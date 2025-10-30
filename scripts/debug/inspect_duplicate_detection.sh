#!/usr/bin/env bash

set -euo pipefail

DEFAULT_CONTAINER="dailydigest-daily-digest-dev-1"
INTERVAL_SECONDS=15
DIGEST_ID=""
LOG_FILE=""

usage() {
  cat <<'USAGE'
Usage: scripts/debug/inspect_duplicate_detection.sh [options]

Options:
  -c <container>   Docker container name (default: dailydigest-daily-digest-dev-1)
  -d <digest_id>   Digest ID to monitor for duplicate detection lifecycle
  -i <seconds>     Sampling interval in seconds while monitoring (default: 15)
  -o <path>        Optional log file to append snapshots (default: stdout only)
  -h               Show this help message

Run the script before、during、after触发快报重复检测，以对比线程/会话释放情况。
当提供 digest ID 时，脚本将轮询数据库检测状态并在状态改变期间抓取多次快照。
USAGE
}

while getopts "c:d:i:o:h" opt; do
  case "$opt" in
    c) DEFAULT_CONTAINER="$OPTARG" ;;
    d) DIGEST_ID="$OPTARG" ;;
    i) INTERVAL_SECONDS="$OPTARG" ;;
    o) LOG_FILE="$OPTARG" ;;
    h)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

CONTAINER="$DEFAULT_CONTAINER"

if ! docker ps --format '{{.Names}}' | grep -Fxq "$CONTAINER"; then
  echo "[ERROR] Container '$CONTAINER' is not running." >&2
  exit 1
fi

# Determine Python binary inside container (prefer python, fallback to python3)
PYTHON_BIN=""
set +e
PYTHON_BIN=$(docker exec "$CONTAINER" bash -lc "command -v python 2>/dev/null")
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN=$(docker exec "$CONTAINER" bash -lc "command -v python3 2>/dev/null")
fi
set -e

if [[ -z "$PYTHON_BIN" ]]; then
  echo "[ERROR] Unable to locate python interpreter inside container '$CONTAINER'." >&2
  exit 1
fi

find_uvicorn_pid() {
  local pid=""
  set +e
  pid=$(docker exec "$CONTAINER" pgrep -f 'uvicorn.*run:app' 2>/dev/null)
  if [[ -z "$pid" ]]; then
    pid=$(docker exec "$CONTAINER" pgrep -f 'uvicorn' 2>/dev/null)
  fi
  if [[ -z "$pid" ]]; then
    pid=$(docker exec "$CONTAINER" pgrep -f 'python .*run.py' 2>/dev/null)
  fi
  set -e
  echo "$pid"
}

UVICORN_PID=$(find_uvicorn_pid)

if [[ -z "$UVICORN_PID" ]]; then
  echo "[ERROR] Unable to locate uvicorn/process within container '$CONTAINER'." >&2
  exit 1
fi

TIMESTAMP() {
  date '+%Y-%m-%d %H:%M:%S'
}

log_block() {
  if [[ -n "$LOG_FILE" ]]; then
    tee -a "$LOG_FILE"
  else
    cat
  fi
}

collect_thread_snapshot() {
  local label="$1"
  {
    echo "========================================"
    echo "[$(TIMESTAMP)] Snapshot: $label"
    echo "Container      : $CONTAINER"
    echo "Target PID     : $UVICORN_PID"
    echo "Python Binary  : $PYTHON_BIN"
    echo "----------------------------------------"

    echo "[ps] Thread list (first 25 entries):"
    docker exec "$CONTAINER" bash -lc "ps -o pid,tid,stat,pcpu,comm -T -p $UVICORN_PID | head -n 26" || echo "  (ps command failed)"

    local thread_count
    thread_count=$(docker exec "$CONTAINER" bash -lc "ps -T -p $UVICORN_PID --no-headers | wc -l" 2>/dev/null || echo "0")
    echo "Total OS threads (ps): $thread_count"

    echo "[python] threading.enumerate():"
    docker exec "$CONTAINER" "$PYTHON_BIN" - <<'PY' 2>/dev/null || echo "  (python threading snapshot failed)"
import threading

threads = list(threading.enumerate())
print(f"Total Python threads: {len(threads)}")
highlight_keywords = ("duplicate", "detector", "digest")
for t in threads:
    name = t.name or "<unnamed>"
    markers = []
    lname = name.lower()
    if any(k in lname for k in highlight_keywords):
        markers.append("*match")
    markers.append("daemon" if t.daemon else "worker")
    print(f"  - {name} (id={t.ident}, status={'alive' if t.is_alive() else 'dead'}, {', '.join(markers)})")
PY

    echo "[python] SQLAlchemy pool status:"
    docker exec "$CONTAINER" "$PYTHON_BIN" - <<'PY' 2>/dev/null || echo "  (python pool status snapshot failed)"
from app.db.session import engine

try:
    status = engine.pool.status()
except Exception as exc:
    status = f"Unable to fetch pool status: {exc}"
print(status)
PY

  } | log_block
}

fetch_digest_status() {
  [[ -z "$DIGEST_ID" ]] && return 0
  docker exec "$CONTAINER" "$PYTHON_BIN" - <<PY 2>/dev/null
from app.db.session import SessionLocal
from app.models.digest import Digest

session = SessionLocal()
try:
    digest = session.get(Digest, $DIGEST_ID)
    if digest is None:
        print("not_found")
    else:
        print(digest.duplicate_detection_status or "unknown")
finally:
    session.close()
PY
}

monitor_digest() {
  local status
  status=$(fetch_digest_status)
  if [[ "$status" == "" ]]; then
    echo "[WARN] Unable to fetch digest status; continuing with single snapshot." | log_block
    collect_thread_snapshot "single"
    return
  fi

  echo "[INFO] Monitoring digest $DIGEST_ID (current status: $status)" | log_block
  collect_thread_snapshot "initial ($status)"

  while true; do
    sleep "$INTERVAL_SECONDS"
    status=$(fetch_digest_status)
    if [[ -z "$status" ]]; then
      echo "[WARN] Lost digest status; stopping monitor." | log_block
      break
    fi
    collect_thread_snapshot "status=$status"
    case "$status" in
      completed|failed|cancelled)
        echo "[INFO] Detected terminal status '$status'." | log_block
        break
        ;;
    esac
  done
}

if [[ -n "$DIGEST_ID" ]]; then
  monitor_digest
else
  collect_thread_snapshot "single"
fi

echo "========================================" | log_block
echo "[DONE] Inspection finished." | log_block
