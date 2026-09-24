from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job

from core.config import settings


class InferenceService:
    @staticmethod
    async def get_pool():
        return await create_pool(RedisSettings(
            host=settings.redis_host,
            port=settings.redis_port,
        ))

    @staticmethod
    async def enqueue_inference(text: str, model_name: str, version: str) -> str:
        """Enqueue run_inference job ไปที่ Inference Worker ผ่าน Redis"""
        pool = await InferenceService.get_pool()
        job = await pool.enqueue_job("run_inference", text, model_name, version, _queue_name="inference_queue")
        await pool.close()
        return job.job_id

    @staticmethod
    async def get_result(job_id: str) -> dict:
        """ดึงผลลัพธ์ของ Inference Job จาก Redis ด้วย job_id"""
        pool = await InferenceService.get_pool()
        job = Job(job_id, pool)
        status = await job.status()
        info = await job.result_info()
        await pool.close()
        return {
            "job_id": job_id,
            "status": status.value,
            "result": info.result if info else None,
        }
