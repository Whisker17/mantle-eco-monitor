#!/usr/bin/env bash
set -euo pipefail

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8000}"
WAIT_SECONDS="${WAIT_SECONDS:-30}"
TMP_DIR="${TMP_DIR:-.tmp}"
SCHEDULER_PROFILE="${SCHEDULER_PROFILE:-dev_live}"
CURL_BIN="${CURL_BIN:-curl}"
PYTHON_BIN="${PYTHON_BIN:-python}"
UVICORN_BIN="${UVICORN_BIN:-uvicorn}"

PID_FILE="${TMP_DIR}/dev_live.pid"
LOG_FILE="${TMP_DIR}/dev_live.log"
HEALTH_URL="http://${APP_HOST}:${APP_PORT}/api/health"
SOURCES_URL="http://${APP_HOST}:${APP_PORT}/api/health/sources"
MNT_METRIC_URL="http://${APP_HOST}:${APP_PORT}/api/metrics/latest?entity=mantle&metric_name=mnt_volume"
TVS_METRIC_URL="http://${APP_HOST}:${APP_PORT}/api/metrics/latest?entity=mantle&metric_name=total_value_secured"


usage() {
  cat <<'EOF'
Usage: ./scripts/dev_live_check.sh <up|check|full|down>
EOF
}


is_port_in_use() {
  if (echo >"/dev/tcp/${APP_HOST}/${APP_PORT}") >/dev/null 2>&1; then
    return 0
  fi
  return 1
}


require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "Missing required environment variable: ${name}" >&2
    return 1
  fi
}


ensure_tmp_dir() {
  mkdir -p "${TMP_DIR}"
}


fetch_json() {
  local url="$1"
  "${CURL_BIN}" --silent --show-error --fail --max-time 2 "${url}"
}


parse_health_summary() {
  local payload="$1"
  "${PYTHON_BIN}" - "${payload}" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
print(data.get("status", "unknown"))
print(data.get("db", "unknown"))
print(data.get("next_scheduled_run") or "none")
PY
}


summarize_sources() {
  local payload="$1"
  "${PYTHON_BIN}" - "${payload}" <<'PY'
import json
import sys

runs = json.loads(sys.argv[1]).get("runs", [])
latest = {}
for run in runs:
    latest.setdefault(run.get("source_platform", "unknown"), run.get("status", "unknown"))

for source_platform in sorted(latest):
    print(f"{source_platform}={latest[source_platform]}")
PY
}


metric_presence() {
  local payload="$1"
  "${PYTHON_BIN}" - "${payload}" <<'PY'
import json
import sys

snapshots = json.loads(sys.argv[1]).get("snapshots", [])
print("present" if snapshots else "missing")
PY
}


start_server() {
  if [ -f "${PID_FILE}" ]; then
    local existing_pid
    existing_pid="$(cat "${PID_FILE}")"
    if [ -n "${existing_pid}" ] && kill -0 "${existing_pid}" >/dev/null 2>&1; then
      echo "dev_live service already running with PID ${existing_pid}"
      return 0
    fi
    rm -f "${PID_FILE}"
  fi

  if is_port_in_use; then
    echo "Port ${APP_PORT} on ${APP_HOST} is already in use" >&2
    return 1
  fi

  (
    export DATABASE_URL
    export SCHEDULER_PROFILE
    exec "${UVICORN_BIN}" src.main:create_app --factory --host "${APP_HOST}" --port "${APP_PORT}"
  ) >>"${LOG_FILE}" 2>&1 &

  local pid="$!"
  echo "${pid}" > "${PID_FILE}"
  echo "Started dev_live service with PID ${pid}"
}


stop_server() {
  if [ ! -f "${PID_FILE}" ]; then
    echo "No managed dev_live service PID file found"
    return 0
  fi

  local pid
  pid="$(cat "${PID_FILE}")"

  if [ -n "${pid}" ] && kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" >/dev/null 2>&1 || true
    for _ in $(seq 1 20); do
      if ! kill -0 "${pid}" >/dev/null 2>&1; then
        break
      fi
      sleep 0.1
    done
    if kill -0 "${pid}" >/dev/null 2>&1; then
      echo "Failed to stop managed PID ${pid}" >&2
      return 1
    fi
  fi

  rm -f "${PID_FILE}"
  echo "Stopped dev_live service"
}


run_scheduler_job() {
  local job_id="$1"
  local output

  if ! output="$(DATABASE_URL="${DATABASE_URL}" SCHEDULER_PROFILE="${SCHEDULER_PROFILE}" "${PYTHON_BIN}" -m src.scheduler run "${job_id}" 2>&1)"; then
    echo "Manual scheduler job failed: ${job_id}" >&2
    if [ -n "${output}" ]; then
      echo "${output}" >&2
    fi
    return 1
  fi

  if [ -n "${output}" ]; then
    echo "${output}"
  fi
}


command_up() {
  require_env DATABASE_URL || return 1
  ensure_tmp_dir
  : >> "${LOG_FILE}"
  start_server
}


command_check() {
  local health_json
  if ! health_json="$(fetch_json "${HEALTH_URL}")"; then
    echo "Failed to reach ${HEALTH_URL}" >&2
    return 2
  fi

  echo "Health"
  local health_summary
  health_summary="$(parse_health_summary "${health_json}")"
  local health_status
  local db_status
  local next_run
  health_status="$(printf '%s\n' "${health_summary}" | sed -n '1p')"
  db_status="$(printf '%s\n' "${health_summary}" | sed -n '2p')"
  next_run="$(printf '%s\n' "${health_summary}" | sed -n '3p')"

  echo "status=${health_status}"
  echo "db=${db_status}"
  echo "next_run=${next_run}"

  echo "Source Jobs"
  for job_id in source_health core_coingecko core_l2beat; do
    echo "running=${job_id}"
    if ! run_scheduler_job "${job_id}"; then
      return 3
    fi
  done

  local sources_json
  if ! sources_json="$(fetch_json "${SOURCES_URL}")"; then
    echo "Failed to reach ${SOURCES_URL}" >&2
    return 2
  fi

  echo "Summary"
  echo "service=up"
  echo "health=${health_status}"
  echo "db=${db_status}"
  echo "next_run=${next_run}"
  while IFS= read -r line; do
    [ -n "${line}" ] && echo "${line}"
  done < <(summarize_sources "${sources_json}")

  local mnt_metric_json
  local tvs_metric_json
  if ! mnt_metric_json="$(fetch_json "${MNT_METRIC_URL}")"; then
    echo "Failed to reach ${MNT_METRIC_URL}" >&2
    return 2
  fi
  if ! tvs_metric_json="$(fetch_json "${TVS_METRIC_URL}")"; then
    echo "Failed to reach ${TVS_METRIC_URL}" >&2
    return 2
  fi

  local mnt_status
  local tvs_status
  mnt_status="$(metric_presence "${mnt_metric_json}")"
  tvs_status="$(metric_presence "${tvs_metric_json}")"

  echo "Metric Checks"
  echo "mnt_volume=${mnt_status}"
  echo "total_value_secured=${tvs_status}"

  if [ "${mnt_status}" != "present" ] || [ "${tvs_status}" != "present" ]; then
    return 4
  fi

  return 0
}


command_full() {
  command_up || return $?

  local elapsed=0
  while [ "${elapsed}" -lt "${WAIT_SECONDS}" ]; do
    if fetch_json "${HEALTH_URL}" >/dev/null 2>&1; then
      command_check || return $?
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  echo "Service did not become ready at ${HEALTH_URL} within ${WAIT_SECONDS} seconds" >&2
  return 2
}


command_down() {
  stop_server
}


main() {
  local command="${1:-}"

  case "${command}" in
    up)
      shift
      command_up "$@"
      ;;
    check)
      shift
      command_check "$@"
      ;;
    full)
      shift
      command_full "$@"
      ;;
    down)
      shift
      command_down "$@"
      ;;
    *)
      usage >&2
      return 1
      ;;
  esac
}


main "$@"
