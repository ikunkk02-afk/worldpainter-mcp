from __future__ import annotations

import argparse
import json
import sys

from .bridge import WorldPainterBridge
from .selftest import run_self_test


def main() -> None:
    parser = argparse.ArgumentParser(prog="worldpainter-mcp")
    parser.add_argument("--doctor", action="store_true", help="check the local WorldPainter bridge")
    parser.add_argument("--self-test", action="store_true", help="run offline algorithm and safety tests")
    args = parser.parse_args()
    if args.doctor:
        report = WorldPainterBridge().doctor()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report.get("ok") else 1)
    if args.self_test:
        ok, report = run_self_test()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if ok else 1)
    from .server import mcp

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
