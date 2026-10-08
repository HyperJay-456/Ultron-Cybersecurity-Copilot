"""Single application launcher for Bug Bounty AI - Local Research Workspace.

Starts the FastAPI server, serves the compiled React single-origin UI,
and opens http://127.0.0.1:8000 automatically in the browser.
"""

import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def verify_frontend_build() -> None:
    """Ensure compiled React bundle exists; run build if missing."""
    repo_root = Path(__file__).resolve().parent
    dist_index = repo_root / "frontend" / "dist" / "index.html"

    if not dist_index.exists():
        print("[Launcher] Compiled frontend bundle not found. Building with npm...")
        frontend_dir = repo_root / "frontend"
        try:
            npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
            subprocess.run([npm_cmd, "run", "build"], cwd=str(frontend_dir), check=True)
            print("[Launcher] Frontend build complete.")
        except Exception as exc:
            print(f"[Launcher] Warning: Automated frontend build failed ({exc}). Using secure fallback template.")


def open_browser_delayed(url: str, delay: float = 1.0) -> None:
    """Open the browser once the server has booted."""
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> None:
    verify_frontend_build()

    from src.dashboard.app import create_dashboard_app
    import uvicorn

    print("=" * 40)
    print("LOCAL BUG BOUNTY AI")
    print("=" * 40)
    print()
    print("Application ready:")
    print()
    print(URL)
    print()
    print("Press Ctrl+C to stop.")
    print()
    print("=" * 40)

    # Spawn background thread to open browser
    opener = threading.Thread(target=open_browser_delayed, args=(URL, 1.2), daemon=True)
    opener.start()

    app = create_dashboard_app()
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
