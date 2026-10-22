"""后台任务管理：进度上报、错误捕获、任务状态持久化。

两种运行模式：

``inline``（默认，桌面版与单机部署）
    任务直接在 API 进程内执行。

``external``（云端多 worker 部署）
    API 只负责把任务写入队列（``status='queued'``），
    由 ``services/worker`` 的独立进程轮询领取执行。
    设置环境变量 ``VC_WORKER_MODE=external`` 启用。
"""

from __future__ import annotations

import asyncio
import os
import traceback
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db import Job, Project, SessionLocal
from .pipeline import STAGE_LABELS, Pipeline


def worker_mode() -> str:
    return (os.getenv("VC_WORKER_MODE") or "inline").strip().lower()


def external_worker() -> bool:
    return worker_mode() == "external"


class JobManager:
    def __init__(self):
        self._tasks: dict[int, asyncio.Task] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """在应用启动时记录主事件循环，之后无论从哪个线程调度都能正确创建任务。"""
        self._loop = loop

    def _spawn(self, coro, job_id: int):
        loop = self._loop
        if loop is None:
            task = asyncio.create_task(coro)
        else:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                task = loop.create_task(coro)
            else:
                # 不在主循环线程里（例如同步端点被放到线程池执行）
                task = asyncio.run_coroutine_threadsafe(coro, loop)
        self._tasks[job_id] = task
        return task

    # ------------------------------------------------------------ 启动

    def start_analysis(self, project_id: int) -> Job:
        db = SessionLocal()
        try:
            job = Job(
                project_id=project_id,
                kind="analyze",
                stage="probe",
                status="queued" if external_worker() else "running",
                progress=0.0,
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            project = db.get(Project, project_id)
            project.status = "analyzing"
            project.error = None
            db.commit()
        finally:
            db.close()

        if not external_worker():
            self._spawn(self._run_analysis(job.id, project_id), job.id)
        return job

    def start_render(self, project_id: int) -> Job:
        db = SessionLocal()
        try:
            job = Job(
                project_id=project_id,
                kind="render",
                stage="tts",
                status="queued" if external_worker() else "running",
                progress=0.0,
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            project = db.get(Project, project_id)
            project.status = "rendering"
            project.error = None
            db.commit()
        finally:
            db.close()

        if not external_worker():
            self._spawn(self._run_render(job.id, project_id), job.id)
        return job

    # ------------------------------------------------------------ 执行

    async def _run_analysis(self, job_id: int, project_id: int) -> None:
        db = SessionLocal()
        try:
            project = db.get(Project, project_id)
            pipeline = Pipeline(db, project, self._reporter(db, job_id))
            await pipeline.analyze()
            project.status = "awaiting_review"
            db.commit()
            self._finish(db, job_id, "review", 1.0, f"已生成 {len(project.shots)} 个镜头，等待审核")
        except Exception as exc:  # noqa: BLE001
            self._fail(db, job_id, project_id, exc)
        finally:
            db.close()
            self._tasks.pop(job_id, None)

    async def _run_render(self, job_id: int, project_id: int) -> None:
        db = SessionLocal()
        try:
            project = db.get(Project, project_id)
            pipeline = Pipeline(db, project, self._reporter(db, job_id))
            result = await pipeline.render()
            project.status = "completed"
            db.commit()
            self._finish(db, job_id, "done", 1.0, f"成片已生成（#{result.render_id}）")
        except Exception as exc:  # noqa: BLE001
            self._fail(db, job_id, project_id, exc)
        finally:
            db.close()
            self._tasks.pop(job_id, None)

    # ------------------------------------------------------------ 进度

    def _reporter(self, db: Session, job_id: int):
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

    def _finish(self, db: Session, job_id: int, stage: str, progress: float, message: str) -> None:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = "done"
        job.stage = stage
        job.progress = progress
        job.message = message
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

    def _fail(self, db: Session, job_id: int, project_id: int, exc: Exception) -> None:
        message = str(exc) or exc.__class__.__name__
        job = db.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            job.error = f"{message}\n{traceback.format_exc()[-1200:]}"
            job.message = message
            job.finished_at = datetime.now(timezone.utc)
        project = db.get(Project, project_id)
        if project is not None:
            project.status = "failed"
            project.error = message
        db.commit()

    # ------------------------------------------------------------ 其它

    def cancel(self, job_id: int) -> bool:
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def is_running(self, project_id: int) -> bool:
        db = SessionLocal()
        try:
            job = (
                db.query(Job)
                .filter(
                    Job.project_id == project_id,
                    Job.status.in_(("queued", "running")),
                )
                .order_by(Job.id.desc())
                .first()
            )
            return job is not None
        finally:
            db.close()

    def recover_interrupted(self) -> None:
        """服务重启后，把残留的 running 任务标记为失败。"""
        db = SessionLocal()
        try:
            jobs = db.query(Job).filter(Job.status == "running").all()
            for job in jobs:
                job.status = "failed"
                job.error = "服务重启导致任务中断，请重新运行"
                job.finished_at = datetime.now(timezone.utc)
                project = db.get(Project, job.project_id)
                if project and project.status in ("analyzing", "rendering"):
                    project.status = "failed"
                    project.error = "服务重启导致任务中断，请重新运行"
            db.commit()
        finally:
            db.close()


manager = JobManager()
