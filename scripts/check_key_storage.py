"""检查密钥在数据库中的存储形式（应为密文，且不含明文）。"""

from __future__ import annotations

import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "station.db"

if not DB.exists():
    print(f"数据库不存在：{DB}")
    raise SystemExit(1)

conn = sqlite3.connect(DB)
print(f"数据库：{DB}\n")
print("--- settings 表 ---")
for key, value, secret in conn.execute("select key, value, is_secret from settings"):
    shown = (value or "")[:64]
    print(f"  {key:<28} secret={secret}  value={shown}")

print("\n--- 明文泄漏检查 ---")
hits = list(
    conn.execute("select key from settings where value like '%DUMMY%' or value like 'sk-%'")
)
print(f"  含明文密钥的记录数 = {len(hits)}  {hits if hits else '(无泄漏)'}")

print("\n--- 解密验证 ---")
sys.path.insert(0, str(ROOT / "services" / "api"))
from app.security import decrypt  # noqa: E402

for key, value in conn.execute("select key, value from settings where is_secret = 1"):
    try:
        plain = decrypt(value)
        shown = plain[:8] + "..." + plain[-4:] if len(plain) > 14 else plain
        print(f"  {key:<28} 可解密 ✓  {shown}")
    except Exception as exc:  # noqa: BLE001
        print(f"  {key:<28} 解密失败 ✗  {exc}")
conn.close()
