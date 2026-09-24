from fastapi import APIRouter, status

from api.jobs.controller import enqueue_job, enqueue_train_job, get_job_status
from api.jobs.schema import EnqueueResponse, JobStatusResponse, TrainResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])
router.add_api_route("/", enqueue_job, methods=["POST"], response_model=EnqueueResponse, status_code=status.HTTP_201_CREATED, summary="Enqueue generic job")
router.add_api_route("/train", enqueue_train_job, methods=["POST"], response_model=TrainResponse, status_code=status.HTTP_201_CREATED, summary="Enqueue training job (supports scheduled start time)")
router.add_api_route("/{job_id}", get_job_status, methods=["GET"], response_model=JobStatusResponse, status_code=status.HTTP_200_OK, summary="Get job status")
