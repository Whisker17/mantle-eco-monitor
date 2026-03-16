from __future__ import annotations

import argparse
import json

from src.admin.bootstrap import bootstrap_initial_history
from src.admin.collect import collect_job
from src.admin.inspect import inspect_alerts, inspect_overview, inspect_runs, inspect_snapshots
from src.admin.rebuild import rebuild_data_quality_history
from src.admin.runtime import run_handler
from src.admin.runtime import build_admin_session_factory, load_settings
from src.admin.seed import seed_alert_spike


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.admin")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_subparsers = inspect_parser.add_subparsers(dest="inspect_command", required=True)

    inspect_subparsers.add_parser("overview")

    snapshots_parser = inspect_subparsers.add_parser("snapshots")
    snapshots_parser.add_argument("--entity")
    snapshots_parser.add_argument("--metric")
    snapshots_parser.add_argument("--limit", type=int, default=20)

    alerts_parser = inspect_subparsers.add_parser("alerts")
    alerts_parser.add_argument("--entity")
    alerts_parser.add_argument("--metric")
    alerts_parser.add_argument("--limit", type=int, default=20)

    runs_parser = inspect_subparsers.add_parser("runs")
    runs_parser.add_argument("--source")
    runs_parser.add_argument("--limit", type=int, default=20)

    collect_parser = subparsers.add_parser("collect")
    collect_subparsers = collect_parser.add_subparsers(dest="collect_command", required=True)
    collect_job_parser = collect_subparsers.add_parser("job")
    collect_job_parser.add_argument("job_id")
    collect_job_parser.add_argument("--dry-run", action="store_true")

    seed_parser = subparsers.add_parser("seed")
    seed_subparsers = seed_parser.add_subparsers(dest="seed_command", required=True)
    alert_spike_parser = seed_subparsers.add_parser("alert-spike")
    alert_spike_parser.add_argument("--entity", required=True)
    alert_spike_parser.add_argument("--metric", required=True)
    alert_spike_parser.add_argument("--previous", required=True)
    alert_spike_parser.add_argument("--current", required=True)
    alert_spike_parser.add_argument(
        "--no-evaluate-rules",
        action="store_false",
        dest="evaluate_rules",
    )
    alert_spike_parser.set_defaults(evaluate_rules=True)

    rebuild_parser = subparsers.add_parser("rebuild")
    rebuild_subparsers = rebuild_parser.add_subparsers(dest="rebuild_command", required=True)
    data_quality_parser = rebuild_subparsers.add_parser("data-quality-history")
    data_quality_parser.add_argument("--apply", action="store_true")
    data_quality_parser.add_argument("--run-jobs", action="store_true")

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_subparsers = bootstrap_parser.add_subparsers(dest="bootstrap_command", required=True)
    initial_history_parser = bootstrap_subparsers.add_parser("initial-history")
    initial_history_parser.add_argument("--apply", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    async def _dispatch(command_args: argparse.Namespace) -> int:
        if command_args.command == "inspect":
            settings = load_settings()
            session_factory = build_admin_session_factory(settings)
            async with session_factory() as session:
                if command_args.inspect_command == "overview":
                    result = await inspect_overview(session)
                elif command_args.inspect_command == "snapshots":
                    result = await inspect_snapshots(
                        session,
                        entity=command_args.entity,
                        metric=command_args.metric,
                        limit=command_args.limit,
                    )
                elif command_args.inspect_command == "alerts":
                    result = await inspect_alerts(
                        session,
                        entity=command_args.entity,
                        metric=command_args.metric,
                        limit=command_args.limit,
                    )
                elif command_args.inspect_command == "runs":
                    result = await inspect_runs(
                        session,
                        source=command_args.source,
                        limit=command_args.limit,
                    )
                else:
                    raise SystemExit(f"Unknown inspect command: {command_args.inspect_command}")
        elif command_args.command == "collect":
            settings = load_settings()
            if command_args.collect_command != "job":
                raise SystemExit(f"Unknown collect command: {command_args.collect_command}")
            result = await collect_job(
                command_args.job_id,
                dry_run=command_args.dry_run,
                settings=settings,
            )
        elif command_args.command == "seed":
            settings = load_settings()
            session_factory = build_admin_session_factory(settings)
            if command_args.seed_command != "alert-spike":
                raise SystemExit(f"Unknown seed command: {command_args.seed_command}")
            result = await seed_alert_spike(
                session_factory,
                entity=command_args.entity,
                metric=command_args.metric,
                previous=command_args.previous,
                current=command_args.current,
                evaluate_rules=command_args.evaluate_rules,
            )
        elif command_args.command == "rebuild":
            settings = load_settings()
            session_factory = build_admin_session_factory(settings)
            if command_args.rebuild_command != "data-quality-history":
                raise SystemExit(f"Unknown rebuild command: {command_args.rebuild_command}")
            result = await rebuild_data_quality_history(
                session_factory,
                settings=settings,
                apply=command_args.apply,
                run_jobs=command_args.run_jobs,
            )
        elif command_args.command == "bootstrap":
            settings = load_settings()
            session_factory = build_admin_session_factory(settings)
            if command_args.bootstrap_command != "initial-history":
                raise SystemExit(f"Unknown bootstrap command: {command_args.bootstrap_command}")
            result = await bootstrap_initial_history(
                session_factory,
                settings=settings,
                apply=command_args.apply,
            )
        else:
            raise SystemExit(f"Unknown command: {command_args.command}")

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    return run_handler(_dispatch, args)


if __name__ == "__main__":
    raise SystemExit(main())
