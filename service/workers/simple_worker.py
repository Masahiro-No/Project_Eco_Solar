"""Simple worker task implementation for ARQ background jobs."""


async def simple_work(ctx: dict, job_data: str) -> str:
    """Process simple background work job.

    Args:
        ctx: ARQ context dictionary containing worker state and configuration.
        job_data: String data payload passed to the job.

    Returns:
        str: Result status message ("Success").
    """
    print("---------------------------------")
    print(f"[WORKER] กำลังประมวลผล Job...")
    print(f"[WORKER] ข้อมูลที่ได้รับ: {job_data}")
    print("---------------------------------")
    return "Success"
