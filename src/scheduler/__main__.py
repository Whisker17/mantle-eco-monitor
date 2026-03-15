from __future__ import annotations

import argparse
import asyncio

from config.settings import Settings
from src.scheduler.jobs import load_scheduler_profile, run_job_now


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.scheduler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("job_id")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = Settings()

    if args.command == "list":
        profile_name, profile = load_scheduler_profile(settings)
        print(f"Active profile: {profile_name}")
        for job_id, job_config in sorted(profile.get("jobs", {}).items()):
            print(f"{job_id}: {job_config.get('mode', 'unspecified')}")
        return 0

    if args.command == "run":
        result = asyncio.run(run_job_now(args.job_id, settings))
        print(result)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
