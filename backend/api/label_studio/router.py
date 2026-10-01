from fastapi import APIRouter, status

from api.label_studio.controller import (
    create_annotation,
    create_project,
    create_task,
    list_annotations,
    list_projects,
    list_tasks,
    submit_ground_truth,
    submit_satellite_annotation,
)
from api.label_studio.schema import (
    AnnotationResponse,
    ProjectResponse,
    SubmitGroundTruthResponse,
    SubmitSatelliteAnnotationResponse,
    TaskResponse,
)

router = APIRouter(prefix="/label-studio", tags=["label-studio"])
router.add_api_route("/projects", list_projects, methods=["GET"], response_model=list[ProjectResponse], status_code=status.HTTP_200_OK)
router.add_api_route("/projects", create_project, methods=["POST"], response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
router.add_api_route("/projects/{project_id}/tasks", list_tasks, methods=["GET"], response_model=list[TaskResponse], status_code=status.HTTP_200_OK)
router.add_api_route("/projects/{project_id}/tasks", create_task, methods=["POST"], response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
router.add_api_route("/projects/{project_id}/tasks/{task_id}/annotations", list_annotations, methods=["GET"], response_model=list[AnnotationResponse], status_code=status.HTTP_200_OK)
router.add_api_route("/projects/{project_id}/tasks/{task_id}/annotations", create_annotation, methods=["POST"], response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
router.add_api_route("/ground-truth/submit", submit_ground_truth, methods=["POST"], response_model=SubmitGroundTruthResponse, status_code=status.HTTP_200_OK)
router.add_api_route("/satellite/submit", submit_satellite_annotation, methods=["POST"], response_model=SubmitSatelliteAnnotationResponse, status_code=status.HTTP_200_OK)
