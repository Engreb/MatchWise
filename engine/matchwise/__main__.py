"""Command line: python -m matchwise [download|backtest|update|all]"""
import argparse
from pathlib import Path

from . import backtest, data, pipeline

APP_DATA = Path(__file__).resolve().parents[2] / "app" / "data"


def main() -> None:
    ap = argparse.ArgumentParser(prog="matchwise")
    ap.add_argument("command", choices=["download", "backtest", "update", "all"],
                    help="download: fetch data · backtest: tune + validate (slow) · update: refresh predictions · all: everything")
    ap.add_argument("--offline", action="store_true", help="skip downloading; use cached files")
    args = ap.parse_args()

    if args.command in ("download", "update", "all") and not args.offline:
        print("Downloading data…")
        data.download()
    if args.command in ("backtest", "all"):
        backtest.run(APP_DATA)
    if args.command in ("update", "all"):
        print("Fitting current models…")
        pipeline.run(APP_DATA, offline=args.offline)


if __name__ == "__main__":
    main()
