#!/usr/bin/env bash
set -euo pipefail

DAEMON="/opt/logmein-hamachi/bin/hamachid"
RUNDIR="/run/logmein-hamachi"
PIDFILE="${RUNDIR}/hamachid.pid"
SOCKFILE="${RUNDIR}/ipc.sock"
LOCKFILE="${RUNDIR}/hamachid.lock"

cleanup_runtime() {
  rm -f "${PIDFILE}" "${SOCKFILE}" "${LOCKFILE}"
}

is_running() {
  if [[ -f "${PIDFILE}" ]]; then
    local pid
    pid="$(cat "${PIDFILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start_daemon() {
  mkdir -p "${RUNDIR}"
  if is_running; then
    exit 0
  fi

  cleanup_runtime
  "${DAEMON}" >/dev/null 2>&1 &

  for _ in $(seq 1 40); do
    if is_running; then
      exit 0
    fi
    sleep 0.25
  done

  echo "hamachid failed to become ready" >&2
  exit 1
}

stop_daemon() {
  local pid=""
  if [[ -f "${PIDFILE}" ]]; then
    pid="$(cat "${PIDFILE}" 2>/dev/null || true)"
  fi

  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
    for _ in $(seq 1 20); do
      if ! kill -0 "${pid}" 2>/dev/null; then
        cleanup_runtime
        exit 0
      fi
      sleep 0.25
    done
    kill -9 "${pid}" 2>/dev/null || true
  else
    killall hamachid 2>/dev/null || true
    sleep 1
  fi

  cleanup_runtime
}

status_daemon() {
  if is_running; then
    echo "hamachid is running"
    exit 0
  fi
  echo "hamachid is not running"
  exit 3
}

case "${1:-}" in
  start)
    start_daemon
    ;;
  stop)
    stop_daemon
    ;;
  restart)
    stop_daemon
    start_daemon
    ;;
  status)
    status_daemon
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}" >&2
    exit 2
    ;;
esac
