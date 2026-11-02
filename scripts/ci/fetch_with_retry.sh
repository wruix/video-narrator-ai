#!/usr/bin/env bash
# RA-32: bounded-retry download with strict SHA-256 verification.
#
# Usage:
#   bash scripts/ci/fetch_with_retry.sh <url> <output> <expected_sha256> <label>
#
# Optional environment overrides (all bounded):
#   FETCH_MAX_ATTEMPTS     default 4    (1..10)
#   FETCH_CONNECT_TIMEOUT  default 20   (seconds)
#   FETCH_MAX_TIME         default 600  (seconds per attempt)
#   FETCH_BACKOFF          default 10   (seconds; linear backoff)
#   FETCH_SPEED_LIMIT      default 1024 (bytes/second)
#   FETCH_SPEED_TIME       default 120  (seconds below limit before abort)
#
# Exit codes:
#   0  download OK and SHA-256 matches
#   1  all attempts failed or checksum never matched
#   2  usage / parameter error
#
# Failure is never masked: after the final attempt the script prints a
# GitHub ::error annotation and exits non-zero. Callers MUST NOT swallow
# failures with a force-success fallback (no `continue-on-error`).

set -u

usage() {
  echo "usage: $0 <url> <output> <expected_sha256> <label>" >&2
  exit 2
}

[ "$#" -eq 4 ] || usage
url=$1
output=$2
expected=$3
label=$4

case "$expected" in
  *[!0-9a-f]*|"")
    echo "::error::[$label] expected SHA-256 must be lowercase hex: '$expected'" >&2
    exit 2
    ;;
esac
if [ "${#expected}" -ne 64 ]; then
  echo "::error::[$label] expected SHA-256 length must be 64, got ${#expected}" >&2
  exit 2
fi

MAX_ATTEMPTS=${FETCH_MAX_ATTEMPTS:-4}
CONNECT_TIMEOUT=${FETCH_CONNECT_TIMEOUT:-20}
MAX_TIME=${FETCH_MAX_TIME:-600}
BACKOFF=${FETCH_BACKOFF:-10}
SPEED_LIMIT=${FETCH_SPEED_LIMIT:-1024}
SPEED_TIME=${FETCH_SPEED_TIME:-120}

is_uint() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

is_uint "$MAX_ATTEMPTS"     || { echo "::error::[$label] FETCH_MAX_ATTEMPTS must be an integer" >&2; exit 2; }
is_uint "$CONNECT_TIMEOUT"  || { echo "::error::[$label] FETCH_CONNECT_TIMEOUT must be an integer" >&2; exit 2; }
is_uint "$MAX_TIME"         || { echo "::error::[$label] FETCH_MAX_TIME must be an integer" >&2; exit 2; }
is_uint "$BACKOFF"          || { echo "::error::[$label] FETCH_BACKOFF must be an integer" >&2; exit 2; }
is_uint "$SPEED_LIMIT"      || { echo "::error::[$label] FETCH_SPEED_LIMIT must be an integer" >&2; exit 2; }
is_uint "$SPEED_TIME"       || { echo "::error::[$label] FETCH_SPEED_TIME must be an integer" >&2; exit 2; }

if [ "$MAX_ATTEMPTS" -lt 1 ] || [ "$MAX_ATTEMPTS" -gt 10 ]; then
  echo "::error::[$label] FETCH_MAX_ATTEMPTS must be 1..10, got $MAX_ATTEMPTS" >&2
  exit 2
fi
if [ "$CONNECT_TIMEOUT" -lt 1 ] || [ "$MAX_TIME" -lt 1 ] || [ "$SPEED_TIME" -lt 1 ]; then
  echo "::error::[$label] timeouts must be >= 1 second" >&2
  exit 2
fi

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum < "$1" 2>/dev/null | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 < "$1" 2>/dev/null | awk '{print $1}'
  else
    return 1
  fi
}

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  echo "[fetch] $label: attempt $attempt/$MAX_ATTEMPTS"
  rm -f "$output"

  if curl --fail --location --silent --show-error \
      --retry 0 \
      --connect-timeout "$CONNECT_TIMEOUT" \
      --max-time "$MAX_TIME" \
      --speed-limit "$SPEED_LIMIT" \
      --speed-time "$SPEED_TIME" \
      --output "$output" "$url"; then
    actual=$(hash_file "$output") || actual=""
    echo "[fetch] $label expected: $expected"
    echo "[fetch] $label actual:   ${actual:-<empty>}"
    if printf '%s' "$actual" | grep -Eq '^[0-9a-f]{64}$' && [ "$actual" = "$expected" ]; then
      echo "[fetch] $label: OK (sha256 verified)"
      exit 0
    fi
    echo "[fetch] $label: checksum mismatch or invalid digest (attempt $attempt/$MAX_ATTEMPTS)" >&2
  else
    rc=$?
    echo "[fetch] $label: curl failed rc=$rc (attempt $attempt/$MAX_ATTEMPTS)" >&2
  fi

  if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
    delay=$((BACKOFF * attempt))
    echo "[fetch] $label: retrying in ${delay}s"
    sleep "$delay"
  fi
  attempt=$((attempt + 1))
done

echo "::error::[$label] download failed after $MAX_ATTEMPTS attempts (url=$url)" >&2
exit 1
