"""SQLite 数据层。

使用 SQLAlchemy Core + 显式 SQLAlchemy ORM 模型，数据库文件默认位于
data/station.db，所有路径可通过 VC_DATA_DIR 覆盖。
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Iterable

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from .config import DB_PATH, ensure_dirs

ensure_dirs()

engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 30},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - 引擎钩子
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _iso(dt: _dt.datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.astimezone(_dt.timezone.utc).isoformat()


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="created")

    # 源视频
    video_filename = Column(String(512))
    video_path = Column(Text)
    video_size = Column(Integer, default=0)
    duration = Column(Float, default=0.0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    fps = Column(Float, default=0.0)
    has_audio = Column(Boolean, default=True)

    # 创作设置
    style = Column(String(64), default="cinematic")
    language = Column(String(16), default="zh-CN")
    aspect = Column(String(16), default="original")
    analysis_model = Column(String(64), default="gemini")
    analysis_model_name = Column(String(128), default="")
    script_model = Column(String(64), default="openai")
    script_model_name = Column(String(128), default="")
    asr_provider = Column(String(64), default="")
    tts_provider = Column(String(64), default="edge")
    voice_id = Column(String(128), default="zh-CN-XiaoxiaoNeural")
    voice_speed = Column(String(16), default="+0%")
    voice_emotion = Column(String(32), default="default")
    bgm_volume = Column(Float, default=0.18)
    subtitle_enabled = Column(Boolean, default=True)
    burn_subtitles = Column(Boolean, default=True)
    user_notes = Column(Text, default="")

    error = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    shots = relationship(
        "Shot", back_populates="project", cascade="all, delete-orphan", order_by="Shot.index"
    )
    jobs = relationship(
        "Job", back_populates="project", cascade="all, delete-orphan", order_by="Job.id"
    )
    renders = relationship(
        "Render", back_populates="project", cascade="all, delete-orphan", order_by="Render.id"
    )


class Shot(Base):
    __tablename__ = "shots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    index = Column(Integer, default=0)
    start = Column(Float, default=0.0)
    end = Column(Float, default=0.0)
    visual = Column(Text, default="")  # 画面描述
    narration = Column(Text, default="")  # 解说词
    dialogue = Column(Text, default="")  # 原始对白
    emotion = Column(String(32), default="default")
    speed = Column(String(16), default="+0%")
    frames = Column(Text, default="[]")  # JSON: 关键帧文件名列表
    tts_audio = Column(Text)  # 单句配音相对路径
    tts_duration = Column(Float, default=0.0)
    locked = Column(Boolean, default=False)  # 人工锁定后不被重新生成覆盖
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="shots")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind = Column(String(32), default="pipeline")  # pipeline | analyze | render
    stage = Column(String(32), default="queued")
    status = Column(String(16), default="running")  # running | done | failed | cancelled
    progress = Column(Float, default=0.0)
    message = Column(Text, default="")
    detail = Column(Text, default="")
    error = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    finished_at = Column(DateTime)

    project = relationship("Project", back_populates="jobs")


class Render(Base):
    __tablename__ = "renders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    video_path = Column(Text)
    subtitle_path = Column(Text)
    duration = Column(Float, default=0.0)
    size = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    voice_track = Column(Text)
    script_path = Column(Text)
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="renders")


class Setting(Base):
    """平台侧配置（模式 B 的系统 Key、默认参数等），value 以加密文本存储。"""

    __tablename__ = "settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text)
    is_secret = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    provider = Column(String(64))
    model = Column(String(128))
    kind = Column(String(32))  # vision | text | tts
    units = Column(Float, default=0.0)
    unit_name = Column(String(32), default="tokens")
    estimated_cost = Column(Float, default=0.0)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)


# ---------------------------------------------------------------- 会话


def init_db() -> None:
    Base.metadata.create_all(engine)

    # 增量升级：新增模型名字段，兼容旧数据库
    with engine.connect() as conn:
        for sql in (
            "ALTER TABLE projects ADD COLUMN analysis_model_name VARCHAR(128) DEFAULT ''",
            "ALTER TABLE projects ADD COLUMN script_model_name VARCHAR(128) DEFAULT ''",
        ):
            try:
                conn.execute(__import__("sqlalchemy").text(sql))
            except Exception:  # noqa: BLE001 - 列已存在则忽略
                pass
        conn.commit()


def session_scope() -> Session:
    return SessionLocal()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def rows_to_dicts(rows: Iterable[Any]) -> list[dict]:
    out = []
    for row in rows:
        d = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        out.append(json.loads(json.dumps(d, default=_default)))
    return out


def _default(o: Any):
    if isinstance(o, _dt.datetime):
        return _iso(o)
    if isinstance(o, bytes):
        return o.hex()
    return str(o)


def project_to_dict(p: Project, include_shots: bool = True) -> dict:
    d = {
        "id": p.id,
        "name": p.name,
        "status": p.status,
        "video_filename": p.video_filename,
        "video_size": p.video_size,
        "duration": p.duration or 0.0,
        "width": p.width or 0,
        "height": p.height or 0,
        "fps": p.fps or 0.0,
        "has_audio": bool(p.has_audio),
        "style": p.style,
        "language": p.language,
        "aspect": p.aspect,
        "analysis_model": p.analysis_model,
        "analysis_model_name": p.analysis_model_name or "",
        "script_model": p.script_model,
        "script_model_name": p.script_model_name or "",
        "asr_provider": p.asr_provider or "",
        "tts_provider": p.tts_provider,
        "voice_id": p.voice_id,
        "voice_speed": p.voice_speed,
        "voice_emotion": p.voice_emotion,
        "bgm_volume": p.bgm_volume,
        "subtitle_enabled": bool(p.subtitle_enabled),
        "burn_subtitles": bool(p.burn_subtitles),
        "user_notes": p.user_notes or "",
        "error": p.error,
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
    }
    if include_shots:
        d["shots"] = [shot_to_dict(s) for s in p.shots]
    return d


def shot_to_dict(s: Shot) -> dict:
    try:
        frames = json.loads(s.frames or "[]")
    except (TypeError, ValueError):
        frames = []
    return {
        "id": s.id,
        "index": s.index,
        "start": round(s.start or 0.0, 3),
        "end": round(s.end or 0.0, 3),
        "duration": round((s.end or 0.0) - (s.start or 0.0), 3),
        "visual": s.visual or "",
        "narration": s.narration or "",
        "dialogue": s.dialogue or "",
        "emotion": s.emotion or "default",
        "speed": s.speed or "+0%",
        "frames": frames,
        "tts_duration": round(s.tts_duration or 0.0, 3),
        "locked": bool(s.locked),
        "updated_at": _iso(s.updated_at),
    }


def render_to_dict(r: Render) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "duration": round(r.duration or 0.0, 3),
        "size": r.size or 0,
        "width": r.width or 0,
        "height": r.height or 0,
        "has_subtitle": bool(r.subtitle_path),
        "created_at": _iso(r.created_at),
    }


def job_to_dict(j: Job) -> dict:
    return {
        "id": j.id,
        "project_id": j.project_id,
        "kind": j.kind,
        "stage": j.stage,
        "status": j.status,
        "progress": round(j.progress or 0.0, 4),
        "message": j.message or "",
        "detail": j.detail or "",
        "error": j.error,
        "created_at": _iso(j.created_at),
        "finished_at": _iso(j.finished_at),
    }
