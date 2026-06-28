#!/usr/bin/env python3
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from codexgpt_bridge.mcp_protocol import serve  # noqa: E402


if __name__ == "__main__":
    serve()
