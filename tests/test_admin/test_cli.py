from __future__ import annotations

import argparse

import pytest

from src.admin.__main__ import _build_parser
from src.admin.runtime import run_async_handler


def test_admin_cli_parses_inspect_overview_command():
    parser = _build_parser()

    args = parser.parse_args(["inspect", "overview"])

    assert args.command == "inspect"
    assert args.inspect_command == "overview"


def test_admin_cli_parses_inspect_snapshots_filters():
    parser = _build_parser()

    args = parser.parse_args(
        ["inspect", "snapshots", "--entity", "mantle", "--metric", "tvl", "--limit", "10"]
    )

    assert args.command == "inspect"
    assert args.inspect_command == "snapshots"
    assert args.entity == "mantle"
    assert args.metric == "tvl"
    assert args.limit == 10


def test_admin_cli_parses_collect_job_command():
    parser = _build_parser()

    args = parser.parse_args(["collect", "job", "core_defillama"])

    assert args.command == "collect"
    assert args.collect_command == "job"
    assert args.job_id == "core_defillama"
    assert args.dry_run is False


def test_admin_cli_parses_seed_alert_spike_command():
    parser = _build_parser()

    args = parser.parse_args(
        [
            "seed",
            "alert-spike",
            "--entity",
            "mantle",
            "--metric",
            "tvl",
            "--previous",
            "100",
            "--current",
            "200",
        ]
    )

    assert args.command == "seed"
    assert args.seed_command == "alert-spike"
    assert args.entity == "mantle"
    assert args.metric == "tvl"
    assert args.previous == "100"
    assert args.current == "200"
    assert args.evaluate_rules is True


@pytest.mark.asyncio
async def test_admin_runtime_runs_async_handler():
    calls: list[argparse.Namespace] = []

    async def handler(args: argparse.Namespace) -> int:
        calls.append(args)
        return 7

    result = await run_async_handler(handler, argparse.Namespace(command="inspect"))

    assert result == 7
    assert calls[0].command == "inspect"
