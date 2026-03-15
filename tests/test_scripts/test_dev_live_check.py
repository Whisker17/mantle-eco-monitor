from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "dev_live_check.sh"


def run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
    )


def make_executable(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def make_fake_curl(
    tmp_path: Path,
    *,
    health_json: str | None = None,
    sources_json: str | None = None,
    mnt_metric_json: str | None = None,
    tvs_metric_json: str | None = None,
) -> Path:
    files: dict[str, str] = {}
    for name, payload in {
        "health": health_json,
        "sources": sources_json,
        "mnt": mnt_metric_json,
        "tvs": tvs_metric_json,
    }.items():
        if payload is None:
            continue
        path = tmp_path / f"{name}.json"
        path.write_text(payload, encoding="utf-8")
        files[name] = str(path)

    lines = [
        "#!/usr/bin/env bash",
        'url="${@: -1}"',
        'case "$url" in',
    ]
    if "sources" in files:
        lines.extend(
            [
                '  *"/api/health/sources"*)',
                f'    cat "{files["sources"]}"',
                "    ;;",
            ]
        )
    if "health" in files:
        lines.extend(
            [
                '  *"/api/health")',
                f'    cat "{files["health"]}"',
                "    ;;",
            ]
        )
    if "mnt" in files:
        lines.extend(
            [
                '  *"metric_name=mnt_volume"*)',
                f'    cat "{files["mnt"]}"',
                "    ;;",
            ]
        )
    if "tvs" in files:
        lines.extend(
            [
                '  *"metric_name=total_value_secured"*)',
                f'    cat "{files["tvs"]}"',
                "    ;;",
            ]
        )
    lines.extend(
        [
            '  *)',
            '    echo "unexpected url: $url" >&2',
            "    exit 6",
            "    ;;",
            "esac",
        ]
    )

    return make_executable(tmp_path / "fake-curl.sh", "\n".join(lines) + "\n")


def make_fake_python(tmp_path: Path) -> Path:
    shim = "\n".join(
        [
            "#!/usr/bin/env bash",
            'if [ "${1:-}" = "-m" ] && [ "${2:-}" = "src.scheduler" ] && [ "${3:-}" = "run" ]; then',
            '  job="${4:-}"',
            '  case "$job" in',
            '    source_health)',
            '      if [ -n "${FAKE_SOURCE_HEALTH_STDOUT:-}" ]; then printf "%s\\n" "${FAKE_SOURCE_HEALTH_STDOUT}"; fi',
            '      exit "${FAKE_SOURCE_HEALTH_EXIT_CODE:-0}"',
            '      ;;',
            '    core_coingecko)',
            '      if [ -n "${FAKE_COINGECKO_STDOUT:-}" ]; then printf "%s\\n" "${FAKE_COINGECKO_STDOUT}"; fi',
            '      exit "${FAKE_COINGECKO_EXIT_CODE:-0}"',
            '      ;;',
            '    core_l2beat)',
            '      if [ -n "${FAKE_L2BEAT_STDOUT:-}" ]; then printf "%s\\n" "${FAKE_L2BEAT_STDOUT}"; fi',
            '      exit "${FAKE_L2BEAT_EXIT_CODE:-0}"',
            '      ;;',
            '    *)',
            '      echo "unexpected scheduler job: ${job}" >&2',
            '      exit 9',
            '      ;;',
            '  esac',
            'fi',
            'exec "${REAL_PYTHON}" "$@"',
        ]
    )
    return make_executable(tmp_path / "fake-python.sh", shim + "\n")


def test_up_exits_with_code_1_when_database_url_is_missing(tmp_path):
    fake_uvicorn = make_executable(
        tmp_path / "fake-uvicorn.sh",
        "#!/usr/bin/env bash\nexit 0\n",
    )

    result = run_script(
        "up",
        env={
            "TMP_DIR": str(tmp_path / ".tmp"),
            "UVICORN_BIN": str(fake_uvicorn),
        },
    )

    assert result.returncode == 1
    assert "DATABASE_URL" in (result.stdout + result.stderr)


def test_check_exits_with_code_2_when_health_endpoint_is_unreachable(tmp_path):
    fake_curl = make_executable(
        tmp_path / "fake-curl.sh",
        "#!/usr/bin/env bash\nexit 7\n",
    )

    result = run_script(
        "check",
        env={
            "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
            "TMP_DIR": str(tmp_path / ".tmp"),
            "CURL_BIN": str(fake_curl),
            "PYTHON_BIN": sys.executable,
        },
    )

    assert result.returncode == 2
    assert "/api/health" in (result.stdout + result.stderr)


def test_unknown_subcommand_exits_non_zero():
    result = run_script("nope")

    assert result.returncode != 0


def test_known_subcommands_are_recognized(tmp_path):
    fake_curl = make_executable(
        tmp_path / "fake-curl.sh",
        "#!/usr/bin/env bash\nexit 7\n",
    )
    fake_uvicorn = make_executable(
        tmp_path / "fake-uvicorn.sh",
        "#!/usr/bin/env bash\nexit 0\n",
    )

    common_env = {
        "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
        "TMP_DIR": str(tmp_path / ".tmp"),
        "CURL_BIN": str(fake_curl),
        "UVICORN_BIN": str(fake_uvicorn),
        "PYTHON_BIN": sys.executable,
    }

    up_result = run_script("up", env=common_env)
    check_result = run_script("check", env=common_env)
    full_result = run_script("full", env=common_env)
    down_result = run_script("down", env=common_env)

    assert up_result.returncode != 127
    assert check_result.returncode != 127
    assert full_result.returncode != 127
    assert down_result.returncode != 127


def test_up_writes_pid_and_log_under_tmp_dir(tmp_path):
    fake_uvicorn = make_executable(
        tmp_path / "fake-uvicorn.sh",
        (
            "#!/usr/bin/env bash\n"
            "trap 'exit 0' TERM INT\n"
            "while true; do sleep 1; done\n"
        ),
    )
    tmp_dir = tmp_path / ".tmp"

    result = run_script(
        "up",
        env={
            "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
            "TMP_DIR": str(tmp_dir),
            "UVICORN_BIN": str(fake_uvicorn),
        },
    )

    assert result.returncode == 0
    assert (tmp_dir / "dev_live.pid").exists()
    assert (tmp_dir / "dev_live.log").exists()

    pid = int((tmp_dir / "dev_live.pid").read_text(encoding="utf-8").strip())
    assert is_pid_alive(pid) is True

    run_script("down", env={"TMP_DIR": str(tmp_dir)})
    for _ in range(20):
        if not is_pid_alive(pid):
            break
        time.sleep(0.1)


def test_down_stops_managed_process_and_removes_pid_file(tmp_path):
    fake_uvicorn = make_executable(
        tmp_path / "fake-uvicorn.sh",
        (
            "#!/usr/bin/env bash\n"
            "trap 'exit 0' TERM INT\n"
            "while true; do sleep 1; done\n"
        ),
    )
    tmp_dir = tmp_path / ".tmp"

    up_result = run_script(
        "up",
        env={
            "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
            "TMP_DIR": str(tmp_dir),
            "UVICORN_BIN": str(fake_uvicorn),
        },
    )

    assert up_result.returncode == 0
    pid_file = tmp_dir / "dev_live.pid"
    pid = int(pid_file.read_text(encoding="utf-8").strip())

    down_result = run_script("down", env={"TMP_DIR": str(tmp_dir)})

    assert down_result.returncode == 0
    assert pid_file.exists() is False

    for _ in range(20):
        if not is_pid_alive(pid):
            break
        time.sleep(0.1)

    assert is_pid_alive(pid) is False


def test_check_returns_code_3_when_source_health_job_fails(tmp_path):
    fake_curl = make_fake_curl(
        tmp_path,
        health_json='{"status":"healthy","db":"connected","next_scheduled_run":"soon","last_source_runs":{}}',
    )
    fake_python = make_fake_python(tmp_path)

    result = run_script(
        "check",
        env={
            "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
            "CURL_BIN": str(fake_curl),
            "PYTHON_BIN": str(fake_python),
            "REAL_PYTHON": sys.executable,
            "FAKE_SOURCE_HEALTH_EXIT_CODE": "9",
        },
    )

    assert result.returncode == 3
    assert "source_health" in (result.stdout + result.stderr)


def test_check_prints_summary_for_successful_health_and_source_jobs(tmp_path):
    fake_curl = make_fake_curl(
        tmp_path,
        health_json=(
            '{"status":"healthy","db":"connected","next_scheduled_run":"2026-03-15T14:02:00+08:00",'
            '"last_source_runs":{"coingecko":{"status":"success","at":"now"}}}'
        ),
        sources_json=(
            '{"runs":['
            '{"source_platform":"coingecko","status":"success","started_at":"now","id":1,"job_name":"core_coingecko","records_collected":1,"error_message":null,"latency_ms":10},'
            '{"source_platform":"l2beat","status":"success","started_at":"now","id":2,"job_name":"core_l2beat","records_collected":1,"error_message":null,"latency_ms":10}'
            ']}'
        ),
    )
    fake_python = make_fake_python(tmp_path)

    result = run_script(
        "check",
        env={
            "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
            "CURL_BIN": str(fake_curl),
            "PYTHON_BIN": str(fake_python),
            "REAL_PYTHON": sys.executable,
            "FAKE_SOURCE_HEALTH_STDOUT": "{'defillama': 'success'}",
            "FAKE_COINGECKO_STDOUT": "{'status': 'ok'}",
            "FAKE_L2BEAT_STDOUT": "{'status': 'ok'}",
        },
    )

    assert result.returncode == 0
    output = result.stdout + result.stderr
    assert "Health" in output
    assert "Source Jobs" in output
    assert "service=up" in output
    assert "db=connected" in output
    assert "coingecko=success" in output
    assert "l2beat=success" in output
