"""One ingestion round at a time.

The round that runs when the worker starts can still be busy when the next scheduled one fires. Two rounds side
by side would store the same weather rows and satellite frames twice, so the second one is skipped.
No database or network here, so the rule can be checked on its own.
"""

from typing import Any, Awaitable, Callable, Optional

ROUND_LOCK_KEY = "ingest:round:running"
ROUND_LOCK_SECONDS = 900  # a round takes 30-90 s; the lock only outlives it when the worker is killed mid-round


async def run_one_at_a_time(pool: Optional[Any], round_: Callable[[], Awaitable[Any]]) -> tuple[bool, Any]:
    """Await round_() while holding the lock in Redis. Returns (False, None) when another round holds it."""
    if pool is None:
        return True, await round_()
    if not await pool.set(ROUND_LOCK_KEY, "1", nx=True, ex=ROUND_LOCK_SECONDS):
        return False, None
    try:
        return True, await round_()
    finally:
        await pool.delete(ROUND_LOCK_KEY)


async def clear_round_lock(pool: Optional[Any]) -> None:
    """At worker start: only this worker runs rounds, so a lock that is still there belongs to a round that was killed."""
    if pool is not None:
        await pool.delete(ROUND_LOCK_KEY)
