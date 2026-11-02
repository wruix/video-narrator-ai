#!/usr/bin/env bash
# RA-32 regression test for scripts/ci/fetch_with_retry.sh
#
# Verifies that the retry helper:
#   1. downloads and verifies a matching SHA-256;
#   2. fails on checksum mismatch (no false success);
#   3. fails on missing source;
#   4. rejects an invalid expected hash;
#   5. enforces the configured attempt cap.
#
# Uses file:// URLs only; no network access required.

set -u

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
HELPER="$ROOT/scripts/ci/fetch_with_retry.sh"
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t fetchretry)
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
no() { echo "FAIL: $1"; fail=$((fail + 1)); }

if [ ! -f "$HELPER" ]; then
  echo "FATAL: helper not found: $HELPER"
  exit 1
fi

printf 'ra32-fetch-retry-fixture\n' > "$TMP/src.bin"
EXPECTED=$(sha256sum < "$TMP/src.bin" 2>/dev/null | awk '{print $1}')
if [ -z "$EXPECTED" ]; then
  EXPECTED=$(shasum -a 256 < "$TMP/src.bin" 2>/dev/null | awk '{print $1}')
fi
if [ -z "$EXPECTED" ]; then
  echo "FATAL: cannot compute fixture SHA-256"
  exit 1
fi

if command -v cygpath >/dev/null 2>&1; then
  URL="file:///$(cygpath -m "$TMP/src.bin")"
else
  URL="file://$TMP/src.bin"
fi

# 1. Success path.
if FETCH_MAX_ATTEMPTS=2 FETCH_BACKOFF=0 bash "$HELPER" "$URL" "$TMP/out1" "$EXPECTED" "unit-success" >"$TMP/log1" 2>&1; then
  if cmp -s "$TMP/src.bin" "$TMP/out1"; then
    ok "success path downloads and verifies"
  else
    no "success path content mismatch"
  fi
else
  no "success path exited non-zero"
fi

# 2. Checksum mismatch must fail.
WRONG="0000000000000000000000000000000000000000000000000000000000000000"
if FETCH_MAX_ATTEMPTS=2 FETCH_BACKOFF=0 bash "$HELPER" "$URL" "$TMP/out2" "$WRONG" "unit-mismatch" >"$TMP/log2" 2>&1; then
  no "checksum mismatch was masked as success"
else
  ok "checksum mismatch fails"
fi

# 3. Missing source must fail.
if FETCH_MAX_ATTEMPTS=1 FETCH_BACKOFF=0 bash "$HELPER" "$URL.missing" "$TMP/out3" "$EXPECTED" "unit-missing" >"$TMP/log3" 2>&1; then
  no "missing source was masked as success"
else
  ok "missing source fails"
fi

# 4. Invalid expected hash must be rejected before downloading.
if FETCH_MAX_ATTEMPTS=1 bash "$HELPER" "$URL" "$TMP/out4" "not-a-hash" "unit-badarg" >"$TMP/log4" 2>&1; then
  no "invalid expected hash accepted"
else
  ok "invalid expected hash rejected"
fi

# 5. Attempt cap must be enforced.
if grep -q "attempt 1/1" "$TMP/log3" && ! grep -q "attempt 2/1" "$TMP/log3"; then
  ok "attempt cap enforced"
else
  no "attempt cap not enforced"
fi

echo "SUMMARY: pass=$pass fail=$fail"
if [ "$fail" -ne 0 ]; then
  exit 1
fi
exit 0
