#!/usr/bin/env python3
"""Start lookBOOK lab_server (API + demo-lab UI on one port)."""
from __future__ import annotations

import os
import webbrowser

from lookbook.lab_server import run_lab_server

PORT = int(os.environ.get("LOOKBOOK_LAB_PORT", "8042"))

if __name__ == "__main__":
    url = f"http://127.0.0.1:{PORT}/"
    print(f"lookBOOK Demo Lab: {url}")
    print(f"Legacy path also works: http://127.0.0.1:{PORT}/demo-lab/index.html")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    run_lab_server(port=PORT)