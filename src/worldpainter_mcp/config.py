from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_wpscript() -> Path | None:
    explicit = os.environ.get("WORLDPAINTER_WPSCRIPT") or os.environ.get("WPSCRIPT_PATH")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    found = shutil.which("wpscript") or shutil.which("wpscript.exe")
    if found:
        candidates.append(Path(found))
    candidates.extend(
        [
            Path(r"C:\Program Files\WorldPainter\wpscript.exe"),
            Path(r"C:\Program Files (x86)\WorldPainter\wpscript.exe"),
            Path(r"D:\WorldPainter\wpscript.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def data_root() -> Path:
    explicit = os.environ.get("WORLDPAINTER_MCP_DATA")
    if explicit:
        root = Path(explicit)
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"]) / "WorldPainterMCP"
    else:
        root = Path.home() / ".worldpainter-mcp"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()
