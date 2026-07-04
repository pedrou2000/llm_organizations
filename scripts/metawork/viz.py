"""Launch the meta-work trajectory visualizer (local web app).

    python scripts/metawork/viz.py                # http://127.0.0.1:8010
    python scripts/metawork/viz.py --port 9000
    python scripts/metawork/viz.py --jobs-dir results/metawork/harbor_jobs

Over SSH, forward the port:  ssh -L 8010:127.0.0.1:8010 <host>
"""
from __future__ import annotations

import argparse

import uvicorn

from metawork.viz.server import create_app


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--jobs-dir", default="results/metawork/harbor_jobs")
    args = ap.parse_args()

    app = create_app(args.jobs_dir)
    print(f"meta-work viz → http://{args.host}:{args.port}")
    # log_level="info" so uvicorn prints "Uvicorn running on http://…:{port}",
    # which is what VSCode's port auto-forwarder detects.
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
