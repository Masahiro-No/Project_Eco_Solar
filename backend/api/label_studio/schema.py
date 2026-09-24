from pydantic import BaseModel


class CreateProjectRequest(BaseModel):
    title: str
    label_config: str  # XML config สำหรับ labeling interface


class ProjectResponse(BaseModel):
    id: int
    title: str
    task_number: int | None = None


class ImportTaskRequest(BaseModel):
    data: dict  # task data payload เช่น {"image": "https://..."}


class TaskResponse(BaseModel):
    id: int
    data: dict
