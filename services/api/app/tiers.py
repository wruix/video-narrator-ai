"""套餐与额度配置。

原则：**代码里不写死任何额度数字**。额度、单价、特性开关全部来自
``config/tiers.yaml``（可用环境变量 ``VC_TIERS_FILE`` 覆盖路径），
这样模型涨价或调整运营策略时只改配置，不必发版。

未提供配置文件时回退到内置的 ``self-hosted`` 档位（不限额度）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .config import ROOT_DIR

DEFAULT_TIERS_FILE = ROOT_DIR / "config" / "tiers.yaml"
FALLBACK_PATH = ROOT_DIR / "config" / "tiers.example.yaml"

# 无配置文件时的兜底定义（自建部署，不限额度）
BUILTIN_TIERS: dict = {
    "version": 1,
    "default_tier": "self-hosted",
    "tiers": {
        "self-hosted": {
            "label": "Self-hosted",
            "label_zh": "自建部署",
            "upload_max_mb": 4096,
            "monthly_video_seconds": 0,
            "concurrent_jobs": 2,
            "byok": True,
            "features": ["local_processing", "srt_export", "all_providers", "api_access"],
        }
    },
    "pricing": {"currency": "USD", "models": {}, "tts": {}, "compute": {}, "storage": {}},
}


@dataclass
class TierConfig:
    id: str
    label: str
    label_zh: str
    upload_max_mb: int = 4096
    monthly_video_seconds: int = 0
    concurrent_jobs: int = 2
    byok: bool = True
    features: list[str] = field(default_factory=list)

    @property
    def upload_max_bytes(self) -> int:
        return self.upload_max_mb * 1024 * 1024

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "label_zh": self.label_zh,
            "upload_max_mb": self.upload_max_mb,
            "monthly_video_seconds": self.monthly_video_seconds,
            "concurrent_jobs": self.concurrent_jobs,
            "byok": self.byok,
            "features": self.features,
        }


@dataclass
class Tiers:
    default_tier: str
    tiers: dict[str, TierConfig]
    pricing: dict
    version: int = 1

    def get(self, tier_id: str | None) -> TierConfig:
        return self.tiers.get(tier_id or self.default_tier) or self.tiers[self.default_tier]

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "default_tier": self.default_tier,
            "tiers": {k: v.to_dict() for k, v in self.tiers.items()},
            "pricing": self.pricing,
        }


def _load_raw() -> dict:
    path = os.getenv("VC_TIERS_FILE")
    candidates = [Path(path)] if path else [DEFAULT_TIERS_FILE, FALLBACK_PATH]
    for candidate in candidates:
        try:
            if candidate and candidate.exists():
                with candidate.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                if isinstance(data, dict) and data.get("tiers"):
                    return data
        except (OSError, yaml.YAMLError) as exc:
            print(f"[tiers] 读取 {candidate} 失败：{exc}")
    return BUILTIN_TIERS


@lru_cache(maxsize=1)
def load_tiers() -> Tiers:
    raw = _load_raw()
    tiers: dict[str, TierConfig] = {}
    for tid, spec in (raw.get("tiers") or {}).items():
        tiers[tid] = TierConfig(
            id=tid,
            label=spec.get("label", tid),
            label_zh=spec.get("label_zh", spec.get("label", tid)),
            upload_max_mb=int(spec.get("upload_max_mb", 4096)),
            monthly_video_seconds=int(spec.get("monthly_video_seconds", 0)),
            concurrent_jobs=int(spec.get("concurrent_jobs", 2)),
            byok=bool(spec.get("byok", True)),
            features=list(spec.get("features") or []),
        )
    default_tier = raw.get("default_tier") or next(iter(tiers), "self-hosted")
    if default_tier not in tiers:
        default_tier = next(iter(tiers))
    return Tiers(
        default_tier=default_tier,
        tiers=tiers,
        pricing=raw.get("pricing") or {},
        version=int(raw.get("version", 1)),
    )


def current_tier() -> TierConfig:
    return load_tiers().get(os.getenv("VC_TIER") or None)
