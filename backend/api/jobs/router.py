from fastapi import APIRouter, status

from api.jobs.controller import (
    cancel_job,
    clear_queue,
    enqueue_job,
    enqueue_train_job,
    get_all_queues_summary,
    get_job_status,
    get_queue_jobs,
    retry_job,
)
from api.jobs.schema import (
    CancelJobResponse,
    ClearQueueResponse,
    EnqueueResponse,
    JobStatusResponse,
    QueueJobsResponse,
    QueueSummaryResponse,
    RetryJobResponse,
    TrainResponse,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Static endpoints first
router.add_api_route(
    "/queues",
    get_all_queues_summary,
    methods=["GET"],
    response_model=list[QueueSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="Summary of All Redis Task Queues",
)
router.add_api_route(
    "/queues/{name}/jobs",
    get_queue_jobs,
    methods=["GET"],
    response_model=QueueJobsResponse,
    status_code=status.HTTP_200_OK,
    summary="List Pending Jobs in a Specific Queue",
)
router.add_api_route(
    "/queues/{name}/clear",
    clear_queue,
    methods=["DELETE"],
    response_model=ClearQueueResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear / Flush All Pending Jobs in a Queue",
)
router.add_api_route(
    "/train",
    enqueue_train_job,
    methods=["POST"],
    response_model=TrainResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue Model Training Job",
)
router.add_api_route(
    "",
    enqueue_job,
    methods=["POST"],
    response_model=EnqueueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue Generic Job",
)
router.add_api_route(
    "/{job_id}/retry",
    retry_job,
    methods=["POST"],
    response_model=RetryJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Retry a Failed Job",
)
router.add_api_route(
    "/{job_id}",
    get_job_status,
    methods=["GET"],
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Job Status and Result",
)
router.add_api_route(
    "/{job_id}",
    cancel_job,
    methods=["DELETE"],
    response_model=CancelJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel / Remove Job from Queue",
)
