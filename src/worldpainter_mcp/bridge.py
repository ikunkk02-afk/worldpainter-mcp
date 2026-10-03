from __future__ import annotations

import json
import os
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .config import find_wpscript


class BridgeError(RuntimeError):
    pass


class WorldPainterBridge:
    def __init__(self, executable: str | Path | None = None) -> None:
        self.executable = Path(executable).resolve() if executable else find_wpscript()
        self.script = Path(__file__).with_name("wp_bridge.js").resolve()

    def doctor(self) -> dict[str, Any]:
        if not self.executable:
            return {"ok": False, "error": "wpscript.exe not found", "hint": "Set WPSCRIPT_PATH to its full path."}
        proc = self._run("ping")
        return {
            "ok": proc.get("ok", False),
            "wpscript": str(self.executable),
            "bridge": str(self.script),
            **proc,
        }

    def inspect(self, world_path: str | Path) -> dict[str, Any]:
        world = self._world(world_path)
        return self._run("inspect", str(world))

    def dump_heightmap(self, world_path: str | Path, dimension: str | None, output: str | Path) -> dict[str, Any]:
        world = self._world(world_path)
        out = Path(output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        result = self._run("dump", str(world), dimension or "", str(out))
        if not out.is_file():
            raise BridgeError("WorldPainter reported success but did not create the height dump")
        return result

    def apply(self, world_path: str | Path, output_path: str | Path, dimension: str | None,
              height_file: str | Path | None, edits_file: str | Path | None) -> dict[str, Any]:
        world = self._world(world_path)
        output = Path(output_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        return self._run(
            "apply", str(world), dimension or "", str(height_file or ""),
            str(edits_file or ""), str(output),
        )

    def _world(self, path: str | Path) -> Path:
        result = Path(path).expanduser().resolve()
        if result.suffix.lower() != ".world":
            raise ValueError("Expected a WorldPainter .world file")
        if not result.is_file():
            raise FileNotFoundError(result)
        return result

    def _run(self, *args: str) -> dict[str, Any]:
        if not self.executable:
            raise BridgeError("wpscript.exe not found; set WPSCRIPT_PATH")
        with tempfile.TemporaryDirectory(prefix="wpmcp-") as temp_dir:
            result_path = Path(temp_dir) / "result.json"
            command = [str(self.executable), str(self.script), str(result_path), *args]
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            proc = subprocess.run(command, capture_output=True, text=True, timeout=900, creationflags=flags)
            if result_path.is_file():
                result = json.loads(result_path.read_text(encoding="utf-8"))
            else:
                result = {"ok": False, "error": "bridge produced no result"}
            if proc.returncode != 0 or not result.get("ok"):
                tail = "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-20:])
                raise BridgeError(f"WorldPainter bridge failed: {result.get('error', tail)}\n{tail}")
            return result


HEADER = struct.Struct(">5s6i")


def read_height_dump(path: str | Path) -> tuple[np.ndarray, dict[str, int]]:
    with Path(path).open("rb") as stream:
        magic, x, y, width, height, min_height, max_height = HEADER.unpack(stream.read(HEADER.size))
        if magic != b"WPHM1":
            raise BridgeError("Invalid WorldPainter height dump")
        count = width * height
        values = np.fromfile(stream, dtype=">f4", count=count).astype(np.float32)
    if values.size != count:
        raise BridgeError("Truncated WorldPainter height dump")
    return values.reshape((height, width)), {
        "x": x, "y": y, "width": width, "height": height,
        "min_height": min_height, "max_height": max_height,
    }


def write_height_target(path: str | Path, heights: np.ndarray, meta: dict[str, int]) -> None:
    target = Path(path)
    with target.open("wb") as stream:
        stream.write(HEADER.pack(
            b"WPHM1", meta["x"], meta["y"], meta["width"], meta["height"],
            meta["min_height"], meta["max_height"],
        ))
        np.asarray(heights, dtype=">f4").tofile(stream)
