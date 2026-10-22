"""VideoNarrator AI · 独立任务 Worker。

云端部署时把重任务从 API 进程剥离：

    VC_WORKER_MODE=external python -m uvicorn app.main:app ...   # API 只入队
    python worker.py                                             # Worker 领取并执行

Worker 直接读写与 API 相同的数据库，因此 API 与 Worker 必须共享
``VC_DATA_DIR``（本地可用同一台机器，云端请用共享卷或把数据库换成 PostgreSQL）。

多实例部署时请保证同一时刻只有一个 Worker 领取同一个任务——领取动作使用
带条件的 UPDATE，天然互斥。
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
API_DIR = REPO_ROOT / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.db import Job, Project, SessionLocal  # noqa: E402
from app.services.pipeline import STAGE_LABELS, Pipeline  # noqa: E402

POLL_INTERVAL = float(os.getenv("VC_WORKER_POLL_INTERVAL", "2"))
MAX_JOBS_PER_RUN = int(os.getenv("VC_WORKER_MAX_JOBS", "0") or 0)  # 0 = 不限

_running = False


def _log(msg: str) -> None:
    print(f"[worker {datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def claim_next() -> tuple[int, str, int] | None:
    """原子地领取一个待执行的任务，返回 (job_id, kind, project_id)。"""
    db = SessionLocal()
    try:
        job = (
            db.query(Job)
            .filter(Job.status == "queued")
            .order_by(Job.id.asc())
            .first()
        )
        if job is None:
            return None
        # 带条件的 UPDATE 保证多 Worker 不会重复领取
        updated = (
            db.query(Job)
            .filter(Job.id == job.id, Job.status == "queued")
            .update({"status": "running"}, synchronize_session=False)
        )
        db.commit()
        if not updated:
            return None
        return job.id, job.kind, job.project_id
    finally:
        db.close()


def _reporter(db, job_id: int):
    def report(progress: float, stage: str, message: str) -> None:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.progress = max(0.0, min(1.0, float(progress)))
        job.stage = stage
        job.message = message
        job.detail = STAGE_LABELS.get(stage, stage)
        db.commit()

    return report


async def run_job(job_id: int, kind: str, project_id: int) -> None:
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if project is None:
            raise RuntimeError(f"项目 {project_id} 不存在")
        pipeline = Pipeline(db, project, _reporter(db, job_id))
        if kind == "analyze":
            await pipeline.analyze()
            project.status = "awaiting_review"
            db.commit()
            message = f"已生成 {len(project.shots)} 个镜头，等待审核"
            stage = "review"
        else:
            result = await pipeline.render()
            project.status = "completed"
            db.commit()
            message = f"成片已生成（#{result.render_id}）"
            stage = "done"

        job = db.get(Job, job_id)
        if job is not None:
            job.status = "done"
            job.stage = stage
            job.progress = 1.0
            job.message = message
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        _log(f"job #{job_id} ({kind}) 完成：{message}")
    except Exception as exc:  # noqa: BLE001
        _log(f"job #{job_id} ({kind}) 失败：{exc}")
        job = db.get(Job, job_id)
        if job is not None:
            import traceback

            job.status = "failed"
            job.error = f"{exc}\n{traceback.format_exc()[-1200:]}"
            job.message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        project = db.get(Project, project_id)
        if project is not None:
            project.status = "failed"
            project.error = str(exc)
            db.commit()
    finally:
        db.close()


async def main() -> int:
    global _running
    _running = True

    def stop(*_args) -> None:
        global _running
        _running = False
        _log("收到退出信号，处理完当前任务后退出")

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, stop)
        except (NotImplementedError, ValueError):
            pass

    _log(f"Worker 启动，轮询间隔 {POLL_INTERVAL}s")
    processed = 0
    while _running:
        claimed = claim_next()
        if claimed is None:
            await asyncio.sleep(POLL_INTERVAL)
            continue
        job_id, kind, project_id = claimed
        _log(f"领取任务 #{job_id} ({kind}, project {project_id})")
        await run_job(job_id, kind, project_id)
        processed += 1
        if MAX_JOBS_PER_RUN and processed >= MAX_JOBS_PER_RUN:
            _log(f"已达到单次上限 {MAX_JOBS_PER_RUN}，退出")
            break
    _log("Worker 已退出")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
