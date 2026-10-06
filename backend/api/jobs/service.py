from typing import Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.constants import in_progress_key_prefix, job_key_prefix, result_key_prefix
from arq.jobs import Job
from fastapi import HTTPException, status

from core.config import settings


KNOWN_QUEUES = ("arq:queue", "arq:queue:train_queue", "arq:queue:inference_queue", "arq:queue:ingest_queue")


class JobService:
    @staticmethod
    async def get_pool() -> ArqRedis:
        return await create_pool(RedisSettings(
            host=settings.redis_host,
            port=settings.redis_port,
            conn_timeout=10,
            retry_on_timeout=True,
        ))

    @staticmethod
    async def _state(pool: ArqRedis, job_id: str) -> tuple[str, Optional[str]]:
        """Where a job is: (in_progress | queued | complete | not_found, key of the queue it waits in).

        arq's own Job.status() only looks in the default queue, and every worker here has its own queue.
        """
        if await pool.exists(in_progress_key_prefix + job_id):
            return "in_progress", None
        for q in KNOWN_QUEUES:
            if await pool.zscore(q, job_id) is not None:
                return "queued", q
        if await pool.exists(result_key_prefix + job_id):
            return "complete", None
        return "not_found", None

    @staticmethod
    async def get_status(job_id: str) -> dict:
        pool = await JobService.get_pool()
        try:
            state, _ = await JobService._state(pool, job_id)
            info = await Job(job_id, pool).result_info()
        finally:
            await pool.close()
        return {"job_id": job_id, "status": state, "result": str(info.result) if info else None}

    # ─── Redis Queue Management ──────────────────────────────────────────────

    @staticmethod
    async def get_all_queues_summary() -> list[dict]:
        """Number of jobs waiting in each queue, counted in Redis."""
        pool = await JobService.get_pool()
        summaries = []

        for q in KNOWN_QUEUES:
            # Check length of sorted set
            pending = await pool.zcard(q)
            q_name = q.replace("arq:queue:", "").replace("arq:queue", "default")
            summaries.append({
                "queue_name": q_name,
                "pending": pending or 0,
                "total_keys": pending or 0,
            })

        await pool.close()
        return summaries

    @staticmethod
    async def get_queue_jobs(queue_name: str) -> dict:
        """Get pending job IDs inside a specific Redis queue."""
        pool = await JobService.get_pool()
        redis_key = "arq:queue" if queue_name == "default" else f"arq:queue:{queue_name}"
        
        job_ids_bytes = await pool.zrange(redis_key, 0, -1)
        job_ids = [j.decode() if isinstance(j, bytes) else str(j) for j in job_ids_bytes]
        
        await pool.close()
        return {
            "queue_name": queue_name,
            "count": len(job_ids),
            "jobs": job_ids,
        }

    @staticmethod
    async def cancel_job(job_id: str) -> dict:
        """Remove a job that is still waiting from its queue. A running or finished job is not touched."""
        pool = await JobService.get_pool()
        try:
            state, queue = await JobService._state(pool, job_id)
            if state == "not_found":
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found")
            if state != "queued":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Job {job_id} is {state}: only a job that is still waiting can be removed from its queue",
                )
            await pool.zrem(queue, job_id)
            await pool.delete(job_key_prefix + job_id)
        finally:
            await pool.close()
        return {"job_id": job_id, "status": "canceled", "message": f"Job {job_id} was waiting and has been removed from its queue."}

    @staticmethod
    async def retry_job(job_id: str) -> dict:
        """Queue a finished job again, in the queue it ran in. Needs its stored result (kept for a limited time)."""
        pool = await JobService.get_pool()
        try:
            info = await Job(job_id, pool).result_info()
            if info is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job {job_id} has no stored result (it never ran, is still waiting, or the result expired): nothing to retry",
                )
            new_job = await pool.enqueue_job(info.function, *info.args, _queue_name=info.queue_name, **info.kwargs)
            if new_job is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job {job_id} could not be queued again")
        finally:
            await pool.close()
        return {"job_id": new_job.job_id, "status": "requeued", "message": f"Job {job_id} queued again as {new_job.job_id}"}

    @staticmethod
    async def clear_queue(queue_name: str) -> dict:
        """Clear/flush all pending jobs inside a queue."""
        pool = await JobService.get_pool()
        redis_key = "arq:queue" if queue_name == "default" else f"arq:queue:{queue_name}"
        
        count = await pool.zcard(redis_key)
        await pool.delete(redis_key)
        await pool.close()

        return {
            "queue_name": queue_name,
            "message": f"Successfully flushed {count} pending jobs from queue '{queue_name}'",
            "removed_count": count or 0,
        }
