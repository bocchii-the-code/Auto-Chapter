# -*- coding: utf-8 -*-
"""Simple launcher script for the local Web UI.

Usage:
    python run_web_ui.py

This script:
1. Starts the FastAPI app defined in web_app.py.
2. Opens http://127.0.0.1:8000 in the default browser.
"""

import threading
import time
import webbrowser

import uvicorn


def _open_browser(url: str) -> None:
    # Wait a bit to give the server time to start
    time.sleep(1.5)
    try:
        webbrowser.open(url)
    except Exception:
        # Ignore any browser-opening errors
        pass


if __name__ == "__main__":
    url = "http://127.0.0.1:8000"
    t = threading.Thread(target=_open_browser, args=(url,), daemon=True)
    t.start()

    uvicorn.run(
        "web_app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
