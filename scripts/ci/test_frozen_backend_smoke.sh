#!/usr/bin/env bash
# RA-34: Windows CI smoke test for the FROZEN backend (vns-server.exe).
#
# Runs the FINAL packaged binary (not source, not spec parsing) with:
#   1. an isolated temp data dir (VC_DATA_DIR)
#   2. a non-default test port (VNS_PORT)
#   3. required-module import gate (built into build_server.py, exit 2)
#   4. real process startup + identity-verified health/ping checks
#   5. VC_DATA_DIR / VC_FRONTEND_DIST effectivity proof
#   6. deliberate port squatting -> hard, fast failure (no foreign Ready)
#   7. missing VC_DATA_DIR in frozen mode -> refusal (no silent fallback)
#   8. process cleanup on every exit path; any FAIL => exit 1
#
# Usage (Git Bash on Windows runner):
#   bash scripts/ci/test_frozen_backend_smoke.sh <path-to-vns-server.exe> <apps/web/dist> [ffmpeg] [ffprobe]
set -u

EXE="${1:?usage: test_frozen_backend_smoke.sh <vns-server.exe> <web-dist> [ffmpeg] [ffprobe]}"
WEBDIST="${2:?missing web-dist dir}"
FFMPEG="${3:-}"
FFPROBE="${4:-}"
[ -f "$EXE" ] || { echo "FATAL: frozen exe not found: $EXE"; exit 1; }
[ -d "$WEBDIST" ] || { echo "FATAL: web dist not found: $WEBDIST"; exit 1; }
command -v curl >/dev/null || { echo "FATAL: curl required"; exit 1; }
PY="${PYTHON:-python}"

PORT=$(( 18000 + RANDOM % 2000 ))
DATA="$(mktemp -d)/vns-data"
NODATA_ROOT="$(mktemp -d)"
mkdir -p "$DATA"

# Git Bash does not convert env-var paths; the frozen exe needs native paths.
winp() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi; }
DATA_W="$(winp "$DATA")"
NODATA_W="$(winp "$NODATA_ROOT")"
WEBDIST_W="$(winp "$WEBDIST")"
FFMPEG_W=""; [ -n "$FFMPEG" ] && FFMPEG_W="$(winp "$FFMPEG")"
FFPROBE_W=""; [ -n "$FFPROBE" ] && FFPROBE_W="$(winp "$FFPROBE")"
PIDS=()
FAIL=0
LOG_DIR="$(mktemp -d)"

cleanup() {
  local p
  for p in "${PIDS[@]:-}"; do
    if [ -n "$p" ]; then
      # Git Bash: kill by pid; also taskkill tree when available
      kill "$p" 2>/dev/null || true
      if command -v taskkill >/dev/null 2>&1; then
        taskkill //PID "$p" //T //F >/dev/null 2>&1 || true
      fi
    fi
  done
  rm -rf "$LOG_DIR" || true
}
trap cleanup EXIT

# Git Bash: bash arrays keep values as single argv items (quotes inside
# ${var:+...} would be taken literally, so use env(1) with an array).
ENVV=(VC_DATA_DIR="$DATA_W" VNS_PORT="$PORT" VC_FRONTEND_DIST="$WEBDIST_W")
[ -n "$FFMPEG_W" ] && ENVV+=(VC_FFMPEG="$FFMPEG_W")
[ -n "$FFPROBE_W" ] && ENVV+=(VC_FFPROBE="$FFPROBE_W")

pass() { echo "  [PASS] $*"; }
fail() { echo "  [FAIL] $*"; FAIL=1; }

wait_health() { # $1=port $2=timeout_s
  local port="$1" timeout="${2:-60}" waited=0
  while [ "$waited" -lt "$timeout" ]; do
    local body
    body="$(curl -sf -m 2 "http://127.0.0.1:${port}/api/health" 2>/dev/null || true)"
    if printf '%s' "$body" | grep -q '"app"[[:space:]]*:[[:space:]]*"VideoNarrator AI"'; then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

echo "=== RA-34 frozen backend smoke ==="
echo "exe=$EXE"
echo "webdist=$WEBDIST"
echo "port=$PORT data=$DATA"

# ---------------------------------------------------------------- scenario A
echo "--- [A] frozen startup with isolated env ---"
env "${ENVV[@]}" \
  "$EXE" >"$LOG_DIR/a.out" 2>&1 &
PIDS+=("$!")
A_PID=$!

if wait_health "$PORT" 90; then
  pass "health+identity on port $PORT"
else
  echo "  startup log:"; sed 's/^/    /' "$LOG_DIR/a.out" | tail -20
  fail "backend not healthy within 90s"
fi

# module import gate: process still alive & no FATAL import line
if grep -q "frozen backend missing required module" "$LOG_DIR/a.out"; then
  fail "required-module import gate fired (media_core/ai_providers missing in bundle)"
else
  pass "required-module imports present"
fi

# ping identity
PING="$(curl -sf -m 3 "http://127.0.0.1:${PORT}/api/ping" || true)"
if printf '%s' "$PING" | grep -q '"app"[[:space:]]*:[[:space:]]*"VideoNarrator AI"'; then
  pass "ping identity ok"
else
  fail "ping identity missing: $PING"
fi

# VC_DATA_DIR effectivity: app.log + station.db created under $DATA
sleep 2
if [ -f "$DATA/logs/app.log" ] && [ -f "$DATA/station.db" ]; then
  pass "VC_DATA_DIR honored (logs/app.log + station.db under injected dir)"
else
  ls -R "$DATA" | sed 's/^/    /'
  fail "VC_DATA_DIR not honored"
fi

# VC_FRONTEND_DIST effectivity: GET / serves the SPA index (not the 404 JSON)
ROOT_HTML="$(curl -sf -m 5 "http://127.0.0.1:${PORT}/" || true)"
if printf '%s' "$ROOT_HTML" | grep -qi '<div id="root"' || printf '%s' "$ROOT_HTML" | grep -qi '<html'; then
  if printf '%s' "$ROOT_HTML" | grep -q '前端尚未构建'; then
    fail "frontend not served (missing_frontend JSON returned)"
  else
    pass "VC_FRONTEND_DIST honored (SPA html served at /)"
  fi
else
  fail "GET / returned nothing usable"
fi

# stop A
kill "$A_PID" 2>/dev/null || true
if command -v taskkill >/dev/null 2>&1; then taskkill //PID "$A_PID" //T //F >/dev/null 2>&1 || true; fi
wait "$A_PID" 2>/dev/null || true

# ---------------------------------------------------------------- scenario B
echo "--- [B] port squatting -> hard failure, no foreign Ready confusion ---"
"$PY" - "$PORT" "$LOG_DIR/squatter.out" <<'PYEOF' &
import socket, sys, time
port = int(sys.argv[1])
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", port)); s.listen(1)
print("squatter listening on", port, flush=True)
time.sleep(60)
PYEOF
PIDS+=("$!")
sleep 2

VC_DATA_DIR="$NODATA_W/data" VNS_PORT="$PORT" VNS_HOST=127.0.0.1 \
  "$EXE" >"$LOG_DIR/b.out" 2>&1 &
B_PID=$!
PIDS+=("$B_PID")
# must fail FAST (bind precheck exit 4), never linger as fake-ready
B_RC="timeout"
for _ in $(seq 1 30); do
  if ! kill -0 "$B_PID" 2>/dev/null; then wait "$B_PID"; B_RC=$?; break; fi
  sleep 1
done
if [ "$B_RC" = "4" ] && grep -q "cannot bind" "$LOG_DIR/b.out"; then
  pass "port conflict refused fast (exit 4, 'cannot bind' message)"
else
  echo "  b exit=$B_RC"; sed 's/^/    /' "$LOG_DIR/b.out" | tail -5
  fail "port conflict not refused as expected (rc=$B_RC)"
fi

# ---------------------------------------------------------------- scenario C
echo "--- [C] frozen mode WITHOUT VC_DATA_DIR -> refusal (no silent fallback) ---"
env -u VC_DATA_DIR VNS_PORT=$((PORT + 1)) VNS_HOST=127.0.0.1 \
  "$EXE" >"$LOG_DIR/c.out" 2>&1 &
PIDS+=("$!")
C_PID=$!
C_RC="timeout"
for _ in $(seq 1 30); do
  if ! kill -0 "$C_PID" 2>/dev/null; then wait "$C_PID"; C_RC=$?; break; fi
  sleep 1
done
if [ "$C_RC" != "0" ] && [ "$C_RC" != "timeout" ] && grep -q "VC_DATA_DIR is required in frozen" "$LOG_DIR/c.out"; then
  pass "missing VC_DATA_DIR refused fast (exit $C_RC, explicit message)"
elif [ "$C_RC" != "0" ] && [ "$C_RC" != "timeout" ]; then
  pass "missing VC_DATA_DIR refused (exit $C_RC) with message: $(grep -m1 VC_DATA_DIR "$LOG_DIR/c.out" || echo see-log)"
else
  echo "  c exit=$C_RC"; tail -5 "$LOG_DIR/c.out" | sed 's/^/    /'
  fail "missing VC_DATA_DIR did NOT refuse (silent fallback possible!)"
fi

echo "======================================="
if [ "$FAIL" -eq 0 ]; then
  echo "SMOKE_RESULT=PASS"
else
  echo "SMOKE_RESULT=FAIL"
fi
exit "$FAIL"
