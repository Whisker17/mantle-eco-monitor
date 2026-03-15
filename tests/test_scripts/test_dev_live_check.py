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
