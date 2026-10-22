"""清理所有项目（开发调试用）。"""

from __future__ import annotations

import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"

items = json.load(urllib.request.urlopen(f"{BASE}/api/projects"))["items"]
for p in items:
    r = urllib.request.Request(f"{BASE}/api/projects/{p['id']}", method="DELETE")
    urllib.request.urlopen(r)
print(f"deleted {len(items)} projects")
