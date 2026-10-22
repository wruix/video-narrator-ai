# VideoNarrator AI · 独立任务 Worker

云端部署时把视频处理这类重任务从 API 进程剥离，API 只负责接收上传与返回进度。

## 运行

```bash
# 终端 1：API（只入队）
VC_WORKER_MODE=external python -m uvicorn app.main:app --host 0.0.0.0 --port 8080

# 终端 2：Worker（领取并执行）
python services/worker/worker.py
```

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `VC_WORKER_MODE` | `inline` | API 侧设为 `external` 时只入队 |
| `VC_WORKER_POLL_INTERVAL` | `2` | 轮询间隔（秒） |
| `VC_WORKER_MAX_JOBS` | `0` | 单次运行最多处理多少任务，0 表示不限 |
| `VC_DATA_DIR` | `./data` | **API 与 Worker 必须共享**同一个数据目录 |

## 存储要求

Worker 直接读写与 API 同一个 SQLite 数据库：

- **单机**：两者在同一台机器、共用 `VC_DATA_DIR` 即可。
- **多机**：SQLite 不适合跨机共享，请把数据库换成 PostgreSQL（`db.py` 里的模型基本可以直接复用），
  或把 `VC_DATA_DIR` 挂到共享存储（NAS / NFS）上。

## 横向扩容

多个 Worker 实例可以同时运行：领取任务用的是带条件的 `UPDATE`
（`WHERE id = ? AND status = 'queued'`），同一任务不会被两个 Worker 同时领取。

视频处理是 CPU 密集型，扩容时优先加 Worker 而不是加 API 实例。
