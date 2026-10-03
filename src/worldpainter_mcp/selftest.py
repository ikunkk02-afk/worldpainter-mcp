from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .bridge import write_height_target
from .project import ProjectService
from .terrain import apply_operations, region_mask, summarize


class FakeBridge:
    def __init__(self) -> None:
        yy, xx = np.mgrid[0:64, 0:64]
        self.heights = (62 + 20 * np.exp(-((xx - 32) ** 2 + (yy - 32) ** 2) / 300) + 2 * np.sin(xx / 4)).astype(np.float32)
        self.meta = {"x": 0, "y": 0, "width": 64, "height": 64, "min_height": -64, "max_height": 320}

    def dump_heightmap(self, world_path: str | Path, dimension: str | None, output: str | Path) -> dict[str, Any]:
        write_height_target(output, self.heights, self.meta)
        return {"ok": True, "dimension": "0 NORMAL DETAIL", "bounds": self.meta}

    def inspect(self, world_path: str | Path) -> dict[str, Any]:
        return {"ok": True, "name": "fixture", "dimensions": [{"name": "Surface", **self.meta}]}

    def apply(self, world_path: str | Path, output_path: str | Path, dimension: str | None,
              height_file: str | Path | None, edits_file: str | Path | None) -> dict[str, Any]:
        shutil.copy2(world_path, output_path)
        return {"ok": True, "output": str(output_path), "height_cells_changed": 1, "paint_cells_written": 0}


def run_self_test() -> tuple[bool, dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        bridge = FakeBridge()
        mask = region_mask(bridge.meta, {"type": "circle", "center_x": 32, "center_y": 32, "radius": 20, "feather": 2}, None)
        operations = [
            {"type": "smooth", "radius": 2, "strength": 0.4},
            {"type": "erosion", "iterations": 2, "talus": 1.0, "strength": 0.5},
            {"type": "ridge_valley", "radius": 5, "strength": 0.3},
            {"type": "raise_lower", "delta": 1.0},
            {"type": "slope_limit", "max_slope": 2.0, "iterations": 2},
            {"type": "coastline_soften", "sea_level": 62, "width": 5, "radius": 2},
        ]
        result = apply_operations(bridge.heights, operations, mask, -64, 320)
        assert np.isfinite(result).all() and result.shape == bridge.heights.shape
        assert not np.array_equal(result, bridge.heights)
        checks.append({"name": "six terrain operations", "ok": True, "summary": summarize(result, 62)})

        with tempfile.TemporaryDirectory(prefix="wpmcp-selftest-") as temp:
            root = Path(temp)
            world = root / "fixture.world"
            world.write_bytes(b"fake-world-project")
            service = ProjectService(bridge=bridge, root=root / "state")  # type: ignore[arg-type]
            planned = service.create_plan(
                str(world), None, [{"type": "smooth", "radius": 2, "strength": 0.5}],
                [{"type": "biome", "biome_id": 4}],
                {"type": "rectangle", "x": 8, "y": 8, "width": 24, "height": 24}, None,
            )
            assert not list(root.glob("*.mcp-*.world"))
            preview = service.preview(planned["plan_id"])
            assert all(Path(p).is_file() for p in preview["images"].values())
            applied = service.apply(planned["plan_id"], preview["preview_id"], None)
            assert Path(applied["output"]).is_file() and Path(applied["output"]) != world
            assert world.read_bytes() == b"fake-world-project"
            restored = service.rollback(applied["snapshot_id"], None)
            assert Path(restored["output"]).read_bytes() == b"fake-world-project"
            checks.append({"name": "plan-preview-snapshot-apply-rollback transaction", "ok": True})

        from .server import mcp
        tool_names = sorted(tool.name for tool in mcp._tool_manager.list_tools())
        assert len(tool_names) == 8 and "wp_apply_terrain_plan" in tool_names
        checks.append({"name": "MCP tool registration", "ok": True, "tools": tool_names})
        return True, {"ok": True, "checks": checks}
    except Exception as error:
        checks.append({"name": "failure", "ok": False, "error": repr(error)})
        return False, {"ok": False, "checks": checks}
