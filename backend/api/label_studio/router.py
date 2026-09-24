from fastapi import APIRouter, status

from api.label_studio.controller import create_project, create_task, list_projects, list_tasks
from api.label_studio.schema import ProjectResponse, TaskResponse

router = APIRouter(prefix="/label-studio", tags=["label-studio"])
router.add_api_route("/projects", list_projects, methods=["GET"], response_model=list[ProjectResponse], status_code=status.HTTP_200_OK)
router.add_api_route("/projects", create_project, methods=["POST"], response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
router.add_api_route("/projects/{project_id}/tasks", list_tasks, methods=["GET"], response_model=list[TaskResponse], status_code=status.HTTP_200_OK)
router.add_api_route("/projects/{project_id}/tasks", create_task, methods=["POST"], response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
