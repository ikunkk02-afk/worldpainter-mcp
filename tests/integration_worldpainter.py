from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from worldpainter_mcp.bridge import WorldPainterBridge
from worldpainter_mcp.config import find_wpscript
from worldpainter_mcp.project import ProjectService


def main() -> None:
    executable = find_wpscript()
    if not executable:
        raise SystemExit("SKIP: wpscript.exe not found")
    fixture_script = Path(__file__).with_name("create_fixture.js").resolve()
    with tempfile.TemporaryDirectory(prefix="wpmcp-integration-") as temp:
        root = Path(temp)
        yy, xx = np.mgrid[0:128, 0:128]
        pixels = np.clip(80 + 100 * np.exp(-((xx - 64) ** 2 + (yy - 64) ** 2) / 1400), 0, 255).astype(np.uint8)
        image_path = root / "fixture.png"
        Image.fromarray(pixels, "L").save(image_path)
        world_path = root / "fixture.world"
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        created = subprocess.run([str(executable), str(fixture_script), str(image_path), str(world_path)],
                                 capture_output=True, text=True, timeout=180, creationflags=flags)
        if created.returncode:
            raise RuntimeError(created.stdout + "\n" + created.stderr)

        bridge = WorldPainterBridge(executable)
        info = bridge.inspect(world_path)
        assert info["dimensions"] and info["name"]
        service = ProjectService(bridge=bridge, root=root / "state")
        planned = service.create_plan(
            str(world_path), None,
            [{"type": "smooth", "radius": 2, "strength": 0.35}, {"type": "raise_lower", "delta": 1}],
            [{"type": "terrain", "terrain": "Grass"}, {"type": "biome", "biome_id": 4}],
            {"type": "circle", "center_x": 64, "center_y": 64, "radius": 24}, None,
        )
        preview = service.preview(planned["plan_id"])
        applied = service.apply(planned["plan_id"], preview["preview_id"], None)
        output = Path(applied["output"])
        assert output.is_file() and output != world_path and world_path.is_file()
        bridge.inspect(output)
        print("WorldPainter integration OK:", applied["bridge"])


if __name__ == "__main__":
    main()
