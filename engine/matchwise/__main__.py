"""Command line: python -m matchwise [download|backtest|update|all|strategies|injuries]"""
import argparse
from pathlib import Path

from . import backtest, data, injuries, pipeline, strategies

APP_DATA = Path(__file__).resolve().parents[2] / "app" / "data"


def main() -> None:
    ap = argparse.ArgumentParser(prog="matchwise")
    ap.add_argument("command", choices=["download", "backtest", "update", "all", "strategies", "injuries"],
                    help="download: fetch data · backtest: tune + validate (slow) · update: refresh predictions · all: everything")
    ap.add_argument("--offline", action="store_true", help="skip downloading; use cached files")
    args = ap.parse_args()

    if args.command in ("download", "update", "all") and not args.offline:
        print("Downloading data…")
        data.download()
    if args.command in ("backtest", "all"):
        backtest.run(APP_DATA)
        strategies.run(APP_DATA)  # keep the money backtest in step with the re-tuned model
    if args.command == "strategies":
        strategies.run(APP_DATA)
    if args.command == "injuries":
        injuries.run(APP_DATA)  # one-off test of whether team news improves predictions
    if args.command in ("update", "all"):
        print("Fitting current models…")
        pipeline.run(APP_DATA, offline=args.offline)


if __name__ == "__main__":
    main()
