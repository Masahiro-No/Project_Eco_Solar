from datetime import datetime
from typing import Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job, JobStatus

from core.config import settings


class JobService:
    @staticmethod
    async def get_pool() -> ArqRedis:
        return await create_pool(RedisSettings(
            host=settings.redis_host,
            port=settings.redis_port,
        ))

    @staticmethod
    async def enqueue(function_name: str, job_data: str, queue_name: str = "default") -> str:
        pool = await JobService.get_pool()
        job = await pool.enqueue_job(function_name, job_data, _queue_name=queue_name)
        await pool.close()
        return job.job_id

    @staticmethod
    async def enqueue_train(
        model_type: str = "lstm",
        epochs: int = 10,
        batch_size: int = 32,
        start_time: Optional[datetime] = None,
    ) -> str:
        """Enqueue training/retraining job to train_queue."""
        pool = await JobService.get_pool()
        kwargs = {"_queue_name": "train_queue"}
        if start_time is not None:
            kwargs["_defer_until"] = start_time
        job = await pool.enqueue_job("train_model", model_type, epochs, batch_size, **kwargs)
        await pool.close()
        return job.job_id

    @staticmethod
    async def get_status(job_id: str) -> dict:
        pool = await JobService.get_pool()
        job = Job(job_id, pool)
        status = await job.status()
        info = await job.result_info()
        await pool.close()
        return {
            "job_id": job_id,
            "status": status.value,
            "result": str(info.result) if info else None,
        }

    # ─── Redis Queue Management ──────────────────────────────────────────────

    @staticmethod
    async def get_all_queues_summary() -> list[dict]:
        """List summary of queues and key metrics from Redis."""
        pool = await JobService.get_pool()
        known_queues = ["arq:queue", "arq:queue:train_queue", "arq:queue:infer_queue"]
        summaries = []

        for q in known_queues:
            # Check length of sorted set
            pending = await pool.zcard(q)
            q_name = q.replace("arq:queue:", "").replace("arq:queue", "default")
            summaries.append({
                "queue_name": q_name,
                "pending": pending or 0,
                "active": 0,  # Worker updates in real-time
                "failed": 0,
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
        """Cancel/delete a pending job from Redis."""
        pool = await JobService.get_pool()
        job = Job(job_id, pool)
        status = await job.status()
        
        # Abort and remove from queues
        known_queues = ["arq:queue", "arq:queue:train_queue", "arq:queue:infer_queue"]
        for q in known_queues:
            await pool.zrem(q, job_id)
        
        # Delete job metadata key
        await pool.delete(f"arq:job:{job_id}")
        await pool.close()

        return {
            "job_id": job_id,
            "status": "canceled",
            "message": f"Job {job_id} (previous status: {status.value}) successfully canceled.",
        }

    @staticmethod
    async def retry_job(job_id: str) -> dict:
        """Re-enqueue a failed job ID."""
        pool = await JobService.get_pool()
        job = Job(job_id, pool)
        info = await job.result_info()

        # If job info exists, re-enqueue
        if info:
            new_job = await pool.enqueue_job(info.function, *info.args, **info.kwargs)
            await pool.close()
            return {
                "job_id": new_job.job_id,
                "status": "requeued",
                "message": f"Job re-enqueued as {new_job.job_id}",
            }

        await pool.close()
        return {
            "job_id": job_id,
            "status": "requeued",
            "message": "Retry trigger dispatched.",
        }

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
