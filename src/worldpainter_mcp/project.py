from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .bridge import WorldPainterBridge, read_height_dump, write_height_target
from .config import data_root
from .terrain import apply_operations, file_sha256, region_mask, render_delta, render_height, summarize
from .hydrology import load_water, write_water


HEIGHT_TYPES = {"smooth", "erosion", "ridge_valley", "raise_lower", "slope_limit", "coastline_soften"}
PAINT_TYPES = {"terrain", "layer", "biome", "plants", "water"}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class ProjectService:
    def __init__(self, bridge: WorldPainterBridge | None = None, root: Path | None = None) -> None:
        self.bridge = bridge or WorldPainterBridge()
        self.root = (root or data_root()).resolve()
        self.plans = self.root / "plans"
        self.snapshots = self.root / "snapshots"
        self.exports = self.root / "exports"
        for directory in (self.plans, self.snapshots, self.exports):
            directory.mkdir(parents=True, exist_ok=True)

    def world_info(self, world_path: str) -> dict[str, Any]:
        result = self.bridge.inspect(world_path)
        result["sha256"] = file_sha256(world_path)
        result["safety"] = "Read-only inspection through WorldPainter wpscript"
        return result

    def export_heightmap(self, world_path: str, dimension: str | None = None,
                         output_path: str | None = None) -> dict[str, Any]:
        world = Path(world_path).resolve()
        stem = f"{world.stem}-{utc_stamp()}"
        raw = self.exports / f"{stem}.wphm"
        bridge_result = self.bridge.dump_heightmap(world, dimension, raw)
        values, meta = read_height_dump(raw)
        image = Path(output_path).resolve() if output_path else self.exports / f"{stem}.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        render_height(values, image)
        return {
            "ok": True, "heightmap_png": str(image), "raw_height_data": str(raw),
            "dimension": bridge_result["dimension"], "bounds": meta,
            "summary": summarize(values),
        }

    def analyze(self, world_path: str, dimension: str | None = None,
                sea_level: float | None = None) -> dict[str, Any]:
        exported = self.export_heightmap(world_path, dimension)
        values, meta = read_height_dump(exported["raw_height_data"])
        return {
            "ok": True, "world": str(Path(world_path).resolve()),
            "dimension": exported["dimension"], "bounds": meta,
            "terrain": summarize(values, sea_level),
            "heightmap_png": exported["heightmap_png"],
        }

    def create_plan(self, world_path: str, dimension: str | None,
                    height_operations: list[dict[str, Any]] | None,
                    paint_operations: list[dict[str, Any]] | None,
                    region: dict[str, Any] | None, mask_path: str | None) -> dict[str, Any]:
        height_ops = height_operations or []
        paint_ops = paint_operations or []
        if not height_ops and not paint_ops:
            raise ValueError("At least one height or paint operation is required")
        for op in height_ops:
            if op.get("type") not in HEIGHT_TYPES:
                raise ValueError(f"Unsupported height operation: {op.get('type')}")
        for op in paint_ops:
            if op.get("type") not in PAINT_TYPES:
                raise ValueError(f"Unsupported paint operation: {op.get('type')}")
            if op["type"] == "terrain" and not op.get("terrain"):
                raise ValueError("terrain paint requires terrain name")
            if op["type"] == "layer" and (not op.get("layer") or "value" not in op):
                raise ValueError("layer paint requires layer and value")
            if op["type"] == "biome" and "biome_id" not in op:
                raise ValueError("biome paint requires biome_id")
            if op['type']=='water' and not op.get('data_path'):
                raise ValueError('water requires data_path (NPZ x,y,bed,water arrays)')
            if op["type"] == "plants":
                if not op.get("layer") or not op.get("plants"):
                    raise ValueError("plants requires a unique layer name and plant definitions")
                if not 0 <= float(op.get("density", 0.25)) <= 1:
                    raise ValueError("Plant density must be between 0 and 1")
                for plant in op["plants"]:
                    if not plant.get("name") or not 1 <= int(plant.get("weight", 1)) <= 32767:
                        raise ValueError("Each plant requires a name and weight 1..32767")
        world = Path(world_path).resolve()
        if not world.is_file() or world.suffix.lower() != ".world":
            raise FileNotFoundError(f"WorldPainter project not found: {world}")
        plan_id = uuid.uuid4().hex
        plan_dir = self.plans / plan_id
        plan_dir.mkdir()
        dump_path = plan_dir / "source.wphm"
        source_hash=file_sha256(world)
        dump_result = self.bridge.dump_heightmap(world, dimension, dump_path)
        if file_sha256(world)!=source_hash:
            raise ValueError('Source changed while reading; create a new plan')
        values, meta = read_height_dump(dump_path)
        max_cells = int(os.environ.get("WORLDPAINTER_MCP_MAX_CELLS", "100000000"))
        if values.size > max_cells:
            shutil.rmtree(plan_dir)
            raise ValueError(f"Dimension has {values.size:,} cells, above safety limit {max_cells:,}")
        effective_paint = []
        mask_hashes = {}
        for path in [mask_path] + [op.get("mask_path") for op in paint_ops]:
            if path:
                resolved = str(Path(path).resolve())
                with Image.open(resolved) as image:
                    if image.size != (meta["width"], meta["height"]):
                        raise ValueError("Mask must match the full dimension's width and height")
                mask_hashes[resolved] = file_sha256(resolved)
        for edit in paint_ops:
            item = dict(edit)
            if item['type']=='water':
                item['data_path']=str(Path(item['data_path']).resolve())
                load_water(item['data_path'],meta)
                mask_hashes[item['data_path']]=file_sha256(item['data_path'])
            item["region"] = item.get("region", region)
            if item.get("mask_path"):
                item["mask_path"] = str(Path(item["mask_path"]).resolve())
            effective_paint.append(item)
        plan = {
            "version": 1, "plan_id": plan_id, "created_at": utc_stamp(), "status": "planned",
            "source_world": str(world), "source_sha256": source_hash,
            "dimension": dump_result["dimension"], "bounds": meta,
            "height_operations": height_ops, "paint_operations": effective_paint,
            "region": region, "mask_path": str(Path(mask_path).resolve()) if mask_path else None,
            "mask_hashes": mask_hashes,
            "source_dump": str(dump_path), "before": summarize(values),
        }
        self._save(plan)
        return {
            "ok": True, "plan_id": plan_id, "status": "planned",
            "source_sha256": plan["source_sha256"], "dimension": plan["dimension"],
            "bounds": meta, "before": plan["before"],
            "next_required_action": "Call wp_preview_terrain_edit with this plan_id before applying.",
        }

    def preview(self, plan_id: str) -> dict[str, Any]:
        plan = self._load(plan_id)
        self._check_masks(plan)
        source, meta = read_height_dump(plan["source_dump"])
        mask = region_mask(meta, plan.get("region"), plan.get("mask_path"))
        target = apply_operations(source, plan["height_operations"], mask, meta["min_height"], meta["max_height"])
        plan_dir = self.plans / plan_id
        target_path = plan_dir / "target.wphm"
        before_path, after_path, delta_path = plan_dir / "before.png", plan_dir / "after.png", plan_dir / "delta.png"
        preview_id = uuid.uuid4().hex
        compiled_paint = []
        paint_affected = 0
        paint_summaries = []
        for index, edit in enumerate(plan["paint_operations"]):
            item = dict(edit)
            edit_mask = region_mask(meta, item.get("region"), plan.get("mask_path"))
            if item.get("mask_path"):
                with Image.open(item["mask_path"]) as external:
                    edit_mask *= np.asarray(external.convert("L"), dtype=np.float32) / 255.0
            if item['type']=='water':
                data=load_water(item['data_path'],meta)
                xs,ys=data['x']-meta['x'],data['y']-meta['y']
                keep=edit_mask[ys,xs]>=0.5
                data={k:v[keep] for k,v in data.items()}
                xs,ys=data['x']-meta['x'],data['y']-meta['y']
                if np.any(data['bed']>target[ys,xs]+0.001):
                    raise ValueError('Water edits only lower beds; raising ground is not supported')
                target[ys,xs]=data['bed']
                edit_mask.fill(0); edit_mask[ys,xs]=1
                water_file=plan_dir/f'water-{index}.wphy'
                write_water(water_file,data)
                item['compiled_water_path']=str(water_file)
                item['water_summary']={'cells':len(xs),'water_min':int(data['water'].min()) if len(xs) else None,'water_max':int(data['water'].max()) if len(xs) else None}
            if item["type"] == "plants":
                # BIT layers: density selects locations, not a layer intensity.
                selected = np.zeros(edit_mask.shape, dtype=bool)
                seed = int(item.get("seed", 1)) & 0xffffffff
                xs = np.arange(meta["width"], dtype=np.uint64) + meta["x"]
                for row in range(meta["height"]):
                    hashed = ((xs & 0xffffffff) * 73856093) ^ (((row + meta["y"]) & 0xffffffff) * 19349663) ^ seed
                    hashed ^= hashed >> 16
                    hashed = (hashed * 2246822519) & 0xffffffff
                    hashed ^= hashed >> 13
                    hashed = (hashed * 3266489917) & 0xffffffff
                    hashed ^= hashed >> 16
                    selected[row] = (edit_mask[row] >= 0.5) & (hashed / 4294967296.0 < float(item.get("density", 0.25)))
                edit_mask = selected.astype(np.float32)
            mask_file = plan_dir / f"paint-mask-{index}.png"
            Image.fromarray((edit_mask.clip(0, 1) * 255).astype(np.uint8), "L").save(mask_file)
            item["compiled_mask_path"] = str(mask_file)
            item["compiled_bounds"] = {key: meta[key] for key in ("x", "y", "width", "height")}
            cells = int((edit_mask >= 0.5).sum())
            active_rows = np.flatnonzero(np.any(edit_mask >= 0.5, axis=1))
            active_cols = np.flatnonzero(np.any(edit_mask >= 0.5, axis=0))
            item["compiled_extent"] = ({"x": meta["x"] + int(active_cols[0]),
                                       "y": meta["y"] + int(active_rows[0]),
                                       "width": int(active_cols[-1] - active_cols[0] + 1),
                                       "height": int(active_rows[-1] - active_rows[0] + 1)}
                                      if cells else {"x": 0, "y": 0, "width": 0, "height": 0})
            paint_affected += cells
            paint_summaries.append({"index": index, "type": item["type"], "cells": cells,
                                    "label": item.get("layer", item.get("terrain", str(item.get("biome_id", "")))),
                                    "mask_preview": str(mask_file)})
            del edit_mask
            compiled_paint.append(item)
        edits_path = plan_dir / "paint_edits.json"
        edits_path.write_text(json.dumps(compiled_paint, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact_paths = [edits_path] + [Path(item["compiled_mask_path"]) for item in compiled_paint]
        artifact_paths += [Path(item['compiled_water_path']) for item in compiled_paint if item['type']=='water']
        write_height_target(target_path, target, meta)
        render_height(source,before_path); render_height(target,after_path); render_delta(source,target,delta_path)
        changed=np.abs(target-source)>0.001
        if plan["height_operations"]:
            artifact_paths.append(target_path)
        plan.update({
            "status": "previewed", "preview_id": preview_id, "target_dump": str(target_path),
            "paint_edits_file": str(edits_path), "after": summarize(target),
            "artifact_hashes": {str(path): file_sha256(path) for path in artifact_paths},
            "preview": {"before": str(before_path), "after": str(after_path), "delta": str(delta_path)},
        })
        self._save(plan)
        delta = target - source
        return {
            "ok": True, "plan_id": plan_id, "preview_id": preview_id, "status": "previewed",
            "changed_cells": int(changed.sum()), "affected_mask_cells": int((mask > 0).sum()),
            "delta_min": float(delta.min()), "delta_max": float(delta.max()),
            "before": plan["before"], "after": plan["after"], "images": plan["preview"],
            "paint_operations": plan["paint_operations"], "paint_affected_cells": paint_affected,
            "paint_summary": paint_summaries,
            "next_required_action": "Review the images, then pass plan_id and preview_id to wp_apply_terrain_plan.",
        }

    def apply(self, plan_id: str, preview_id: str, output_path: str | None,
              overwrite_original: bool = False, allow_overwrite_output: bool = False) -> dict[str, Any]:
        plan = self._load(plan_id)
        if plan.get("status") != "previewed" or plan.get("preview_id") != preview_id:
            raise ValueError("A matching current preview_id is required before any write")
        source = Path(plan["source_world"])
        current_hash = file_sha256(source)
        if current_hash != plan["source_sha256"]:
            raise ValueError("Source .world changed after planning; create a new plan")
        self._check_masks(plan)
        for artifact, expected_hash in plan.get("artifact_hashes", {}).items():
            if file_sha256(artifact) != expected_hash:
                raise ValueError("Compiled preview changed; preview the plan again")
        if output_path:
            output = Path(output_path).resolve()
        elif overwrite_original:
            output = source
        else:
            output = source.with_name(f"{source.stem}.mcp-{utc_stamp()}.world")
        if output == source and not overwrite_original:
            raise ValueError("Refusing to overwrite the original unless overwrite_original=true")
        if output.suffix.lower() != ".world":
            raise ValueError("Output must be a .world file")
        if output.exists() and output != source and not allow_overwrite_output:
            raise FileExistsError(f"Output already exists: {output}")
        snapshot_id = uuid.uuid4().hex
        snapshot = self.snapshots / f"{snapshot_id}-{source.name}"
        shutil.copy2(source, snapshot)
        metadata = {
            "snapshot_id": snapshot_id, "snapshot": str(snapshot), "source": str(source),
            "source_sha256": plan["source_sha256"], "created_at": utc_stamp(), "plan_id": plan_id,
        }
        snapshot.with_suffix(snapshot.suffix + ".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        result = self.bridge.apply(
            source, output, plan["dimension"],
            plan["target_dump"] if plan["height_operations"] else None,
            plan["paint_edits_file"] if plan["paint_operations"] else None,
        )
        plan.update({"status": "applied", "applied_at": utc_stamp(), "output": str(output), "snapshot_id": snapshot_id})
        self._save(plan)
        return {"ok": True, "plan_id": plan_id, "output": str(output), "snapshot_id": snapshot_id,
                "original_overwritten": output == source, "bridge": result}

    @staticmethod
    def _check_masks(plan: dict[str, Any]) -> None:
        for path, expected in plan.get("mask_hashes", {}).items():
            if file_sha256(path) != expected:
                raise ValueError("Mask changed after planning; create a new plan")

    def list_snapshots(self, world_path: str | None = None) -> dict[str, Any]:
        target = str(Path(world_path).resolve()) if world_path else None
        entries = []
        for metadata_path in sorted(self.snapshots.glob("*.world.json"), reverse=True):
            item = json.loads(metadata_path.read_text(encoding="utf-8"))
            if target is None or item["source"] == target:
                entries.append(item)
        return {"ok": True, "snapshots": entries}

    def rollback(self, snapshot_id: str, output_path: str | None,
                 overwrite_original: bool = False) -> dict[str, Any]:
        matches = list(self.snapshots.glob(f"{snapshot_id}-*.world"))
        if len(matches) != 1:
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")
        snapshot = matches[0]
        metadata = json.loads(snapshot.with_suffix(snapshot.suffix + ".json").read_text(encoding="utf-8"))
        original = Path(metadata["source"])
        output = Path(output_path).resolve() if output_path else (
            original if overwrite_original else original.with_name(f"{original.stem}.rollback-{utc_stamp()}.world")
        )
        if output == original and not overwrite_original:
            raise ValueError("Refusing to overwrite the original unless overwrite_original=true")
        if output.exists() and output != original:
            raise FileExistsError(f"Rollback output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot, output)
        return {"ok": True, "snapshot_id": snapshot_id, "output": str(output), "original_overwritten": output == original}

    def _plan_path(self, plan_id: str) -> Path:
        if not plan_id or any(c not in "0123456789abcdef" for c in plan_id.lower()):
            raise ValueError("Invalid plan_id")
        return self.plans / plan_id / "plan.json"

    def _load(self, plan_id: str) -> dict[str, Any]:
        path = self._plan_path(plan_id)
        if not path.is_file():
            raise FileNotFoundError(f"Plan not found: {plan_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, plan: dict[str, Any]) -> None:
        path = self._plan_path(plan["plan_id"])
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
