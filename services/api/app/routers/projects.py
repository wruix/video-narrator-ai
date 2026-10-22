"""项目接口：上传、镜头文案编辑、审核、配音与成片导出。"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import ALLOWED_VIDEO_EXT, MAX_UPLOAD_BYTES, OUTPUT_DIR, UPLOAD_DIR, WORK_DIR
from ..db import (
    Job,
    Project,
    Render,
    Shot,
    get_db,
    job_to_dict,
    project_to_dict,
    render_to_dict,
    shot_to_dict,
)
from ..services import keyvault
from ..services.jobs import manager
from ..tiers import current_tier
from ai_providers import ProviderError, get_text
from media_core.media import probe

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------- 工具


def get_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def project_upload_dir(project_id: int) -> Path:
    return UPLOAD_DIR / f"project_{project_id}"


def project_work_dir(project_id: int) -> Path:
    return WORK_DIR / f"project_{project_id}"


def _range_response(path: Path, request: Request, media_type: str) -> Response:
    """支持 Range 请求的文件响应，供视频预览拖动进度条。"""
    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type=media_type, filename=path.name)

    m = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
    if not m:
        return FileResponse(path, media_type=media_type, filename=path.name)

    start_s, end_s = m.groups()
    if start_s:
        start = int(start_s)
        end = int(end_s) if end_s else file_size - 1
    else:
        # bytes=-N 表示最后 N 字节
        length = int(end_s or 0)
        start = max(0, file_size - length)
        end = file_size - 1
    end = min(end, file_size - 1)
    if start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    chunk = 1024 * 256

    def iterator():
        remaining = end - start + 1
        with path.open("rb") as fh:
            fh.seek(start)
            while remaining > 0:
                data = fh.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }
    return StreamingResponse(iterator(), status_code=206, headers=headers, media_type=media_type)


# ---------------------------------------------------------------- 项目 CRUD


class ProjectCreate(BaseModel):
    name: str = "未命名项目"


class ProjectUpdate(BaseModel):
    name: str | None = None
    style: str | None = None
    language: str | None = None
    aspect: str | None = None
    analysis_model: str | None = None
    script_model: str | None = None
    asr_provider: str | None = None
    tts_provider: str | None = None
    voice_id: str | None = None
    voice_speed: str | None = None
    voice_emotion: str | None = None
    bgm_volume: float | None = None
    subtitle_enabled: bool | None = None
    burn_subtitles: bool | None = None
    user_notes: str | None = None


@router.post("")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name.strip() or "未命名项目")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_to_dict(project)


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    rows = db.query(Project).order_by(Project.id.desc()).all()
    return {"items": [project_to_dict(p, include_shots=False) for p in rows]}


@router.get("/{project_id}")
def get_project_detail(project_id: int, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    data = project_to_dict(project)
    data["jobs"] = [
        job_to_dict(j)
        for j in db.query(Job)
        .filter(Job.project_id == project_id)
        .order_by(Job.id.desc())
        .limit(10)
        .all()
    ]
    data["renders"] = [
        render_to_dict(r)
        for r in db.query(Render)
        .filter(Render.project_id == project_id)
        .order_by(Render.id.desc())
        .all()
    ]
    return data


@router.patch("/{project_id}")
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    data = payload.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(project, k, v)
    db.commit()
    db.refresh(project)
    return project_to_dict(project)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    for d in (
        project_upload_dir(project_id),
        project_work_dir(project_id),
        OUTPUT_DIR / f"project_{project_id}",
    ):
        try:
            if d.exists():
                import shutil

                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass
    db.delete(project)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 上传


@router.post("/{project_id}/video")
async def upload_video(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = get_project(db, project_id)
    filename = Path(file.filename or "video.mp4").name
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的格式 {ext or '(未知)'}，请上传 {'/'.join(sorted(ALLOWED_VIDEO_EXT))}",
        )

    target_dir = project_upload_dir(project_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"source{ext}"

    # 上传大小受当前套餐额度限制（额度来自 config/tiers.yaml）
    max_bytes = min(MAX_UPLOAD_BYTES, current_tier().upload_max_bytes)

    size = 0
    with target.open("wb") as fh:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                fh.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="文件超出大小限制")
            fh.write(chunk)

    project.video_filename = filename
    project.video_path = str(target)
    project.video_size = size
    project.status = "uploaded"
    project.error = None
    db.commit()

    # 立即探测一次，让用户在分析之前就能看到时长与分辨率
    try:
        info = await probe(target)
        project.duration = info.duration
        project.width = info.width
        project.height = info.height
        project.fps = info.fps
        project.has_audio = info.has_audio
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 探测失败不阻断上传
        db.refresh(project)
        project.error = f"视频信息探测失败：{exc}"
        db.commit()

    db.refresh(project)
    return {"ok": True, "size": size, "project": project_to_dict(project, include_shots=False)}


@router.get("/{project_id}/video")
def stream_video(project_id: int, request: Request, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project.video_path or not Path(project.video_path).exists():
        raise HTTPException(status_code=404, detail="尚未上传视频")
    media_type = mimetypes.guess_type(project.video_path)[0] or "video/mp4"
    return _range_response(Path(project.video_path), request, media_type)


# ---------------------------------------------------------------- 镜头


@router.get("/{project_id}/shots")
def list_shots(project_id: int, db: Session = Depends(get_db)):
    get_project(db, project_id)  # 校验项目存在
    shots = db.query(Shot).filter(Shot.project_id == project_id).order_by(Shot.index).all()
    return {"items": [shot_to_dict(s) for s in shots]}


class ShotUpdate(BaseModel):
    narration: str | None = None
    visual: str | None = None
    dialogue: str | None = None
    emotion: str | None = None
    speed: str | None = None
    locked: bool | None = None
    start: float | None = None
    end: float | None = None


@router.patch("/{project_id}/shots/{shot_id}")
def update_shot(
    project_id: int, shot_id: int, payload: ShotUpdate, db: Session = Depends(get_db)
):
    get_project(db, project_id)
    shot = db.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise HTTPException(status_code=404, detail="镜头不存在")
    data = payload.model_dump(exclude_none=True)
    for k, v in data.items():
        setattr(shot, k, v)
    db.commit()
    db.refresh(shot)
    return shot_to_dict(shot)


class RegeneratePayload(BaseModel):
    provider: str | None = None
    instruction: str = ""


@router.post("/{project_id}/shots/{shot_id}/regenerate")
async def regenerate_shot(
    project_id: int, shot_id: int, payload: RegeneratePayload, db: Session = Depends(get_db)
):
    project = get_project(db, project_id)
    shot = db.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise HTTPException(status_code=404, detail="镜头不存在")

    provider_id = payload.provider or project.script_model or project.analysis_model
    key, _ = keyvault.resolve_key(db, provider_id)
    provider = get_text(provider_id)
    if provider.spec.requires_key and not key:
        raise HTTPException(status_code=400, detail=f"尚未配置 {provider.spec.name} 的密钥")

    prompt = (
        "请为下面这个镜头写一段视频解说词。\n"
        f"画面：{shot.visual or '（无）'}\n"
        f"原始对白：{shot.dialogue or '（无）'}\n"
        f"当前解说：{shot.narration or '（无）'}\n"
        f"风格：{project.style}\n"
        f"要求：15-45 字，口语化，有画面感，不要出现「这个视频」等前缀。"
    )
    if payload.instruction:
        prompt += f"\n额外要求：{payload.instruction}"

    from ai_providers.base import TextRequest

    try:
        text, usage = await provider.complete(
            TextRequest(
                prompt=prompt,
                system="你是专业的视频解说撰稿人。",
                key=key,
                temperature=0.9,
                max_tokens=600,
            )
        )
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    shot.narration = (text or "").strip()
    db.commit()
    db.refresh(shot)
    return shot_to_dict(shot)


# ---------------------------------------------------------------- 分析 / 审核 / 渲染


@router.post("/{project_id}/analyze")
async def start_analysis(project_id: int, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project.video_path or not Path(project.video_path).exists():
        raise HTTPException(status_code=400, detail="请先上传视频")
    if manager.is_running(project_id):
        raise HTTPException(status_code=409, detail="当前项目已有任务在运行")
    job = manager.start_analysis(project_id)
    return job_to_dict(job)


@router.post("/{project_id}/approve")
def approve_script(project_id: int, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    shots = db.query(Shot).filter(Shot.project_id == project_id).count()
    if not shots:
        raise HTTPException(status_code=400, detail="尚无镜头文案")
    empty = (
        db.query(Shot)
        .filter(Shot.project_id == project_id)
        .filter((Shot.narration.is_(None)) | (Shot.narration == ""))
        .count()
    )
    project.status = "approved"
    db.commit()
    return {"ok": True, "shots": shots, "empty": empty}


@router.post("/{project_id}/render")
async def start_render(project_id: int, db: Session = Depends(get_db)):
    get_project(db, project_id)  # 校验项目存在
    shots = db.query(Shot).filter(Shot.project_id == project_id).count()
    if not shots:
        raise HTTPException(status_code=400, detail="请先完成视频分析")
    if manager.is_running(project_id):
        raise HTTPException(status_code=409, detail="当前项目已有任务在运行")
    job = manager.start_render(project_id)
    return job_to_dict(job)


@router.get("/{project_id}/jobs")
def list_jobs(project_id: int, db: Session = Depends(get_db)):
    jobs = (
        db.query(Job).filter(Job.project_id == project_id).order_by(Job.id.desc()).limit(30).all()
    )
    return {"items": [job_to_dict(j) for j in jobs]}


@router.get("/{project_id}/jobs/{job_id}")
def get_job(project_id: int, job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_to_dict(job)


# ---------------------------------------------------------------- 成片


@router.get("/{project_id}/renders")
def list_renders(project_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(Render).filter(Render.project_id == project_id).order_by(Render.id.desc()).all()
    )
    return {"items": [render_to_dict(r) for r in rows]}


def _get_render(db: Session, project_id: int, render_id: int) -> Render:
    render = db.get(Render, render_id)
    if render is None or render.project_id != project_id:
        raise HTTPException(status_code=404, detail="成片不存在")
    return render


@router.get("/{project_id}/renders/{render_id}/download")
def download_render(project_id: int, render_id: int, db: Session = Depends(get_db)):
    render = _get_render(db, project_id, render_id)
    path = Path(render.video_path or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="成片文件已丢失")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/{project_id}/renders/{render_id}/preview")
def preview_render(project_id: int, render_id: int, request: Request, db: Session = Depends(get_db)):
    render = _get_render(db, project_id, render_id)
    path = Path(render.video_path or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="成片文件已丢失")
    return _range_response(path, request, "video/mp4")


@router.get("/{project_id}/renders/{render_id}/subtitle")
def download_subtitle(project_id: int, render_id: int, db: Session = Depends(get_db)):
    render = _get_render(db, project_id, render_id)
    if not render.subtitle_path or not Path(render.subtitle_path).exists():
        raise HTTPException(status_code=404, detail="该成片没有字幕文件")
    return FileResponse(
        Path(render.subtitle_path),
        media_type="text/plain",
        filename=f"subtitle_{project_id}_{render_id}.srt",
    )


@router.get("/{project_id}/shots/{shot_id}/audio")
def shot_audio(project_id: int, shot_id: int, request: Request, db: Session = Depends(get_db)):
    shot = db.get(Shot, shot_id)
    if shot is None or shot.project_id != project_id:
        raise HTTPException(status_code=404, detail="镜头不存在")
    if not shot.tts_audio:
        raise HTTPException(status_code=404, detail="该镜头尚未生成配音")
    path = project_work_dir(project_id) / "tts" / shot.tts_audio
    if not path.exists():
        raise HTTPException(status_code=404, detail="配音文件已丢失")
    return _range_response(path, request, "audio/mpeg")


@router.get("/{project_id}/frames/{filename}")
def get_frame(project_id: int, filename: str, db: Session = Depends(get_db)):
    safe = Path(filename).name
    path = project_work_dir(project_id) / "frames" / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="画面不存在")
    return FileResponse(path, media_type="image/jpeg")
