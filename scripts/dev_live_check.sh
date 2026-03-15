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
    for _ in $(seq 1 50); do
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


command_up() {
  require_env DATABASE_URL || return 1
  ensure_tmp_dir
  : >> "${LOG_FILE}"
  start_server
}


command_check() {
  if ! "${CURL_BIN}" --silent --show-error --fail --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "Failed to reach ${HEALTH_URL}" >&2
    return 2
  fi

  return 0
}


command_full() {
  command_up || return $?
  command_check || return $?
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
