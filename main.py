"""Launch the weighment entry viewer + labelling GUI and open it in the browser.

Usage (venv active, from the repo root):
    python main.py                 # starts http://127.0.0.1:5050 and opens it
    python main.py --no-browser    # start the server only

All settings live in development/config.yaml -> viewer:. The app itself is
development/entry_viewer/app.py (see development/README.md).
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "development"))

from aws_s3 import load_dotenv_file  # noqa: E402
from entry_viewer.app import create_app, load_config  # noqa: E402

CONFIG_PATH = REPO_ROOT / "development" / "config.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    load_dotenv_file()
    app = create_app(config)

    host, port = config["viewer"]["host"], int(config["viewer"]["port"])
    url = f"http://{host}:{port}"
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    print(f"Entry viewer on {url}  (Ctrl+C to stop)")
    app.run(host=host, port=port, threaded=True, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
