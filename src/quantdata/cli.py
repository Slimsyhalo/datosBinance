import argparse
import json
from pathlib import Path

from .acquire import atomic_json, download, plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["plan", "download", "audit", "trades-audit", "macro", "assets", "l2"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="config/research.json")
    parser.add_argument("--categories", nargs="+")
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    config = json.loads((root / args.config).read_text())
    if args.command == "plan":
        atomic_json(root / "manifests/requested.json", plan(config))
    elif args.command == "download":
        download(config, root, args.workers, args.categories, args.symbols)
    elif args.command == "audit":
        from .research import audit
        audit(config, root)
    elif args.command == "trades-audit":
        from .trades import audit_trades
        audit_trades(config, root)
    elif args.command == "macro":
        from .macro import acquire_macro
        acquire_macro(config, root)
    elif args.command == "assets":
        from .publish import assets
        assets(root)
    elif args.command == "l2":
        from .live import capture
        import asyncio
        asyncio.run(capture(root, args.symbols or config["symbols"], args.seconds))


if __name__ == "__main__":
    main()
