from label_studio_sdk.client import LabelStudio

from core.config import settings


def get_ls_client() -> LabelStudio:
    """สร้าง Label Studio SDK client จาก settings."""
    return LabelStudio(base_url=settings.label_studio_url, api_key=settings.label_studio_api_key)


class LabelStudioService:
    def __init__(self) -> None:
        self.client = get_ls_client()

    def list_projects(self) -> list:
        """คืนรายการ projects ทั้งหมด."""
        return list(self.client.projects.list())

    def create_project(self, title: str, label_config: str):
        """สร้าง project ใหม่."""
        return self.client.projects.create(title=title, label_config=label_config)

    def list_tasks(self, project_id: int) -> list:
        """คืนรายการ tasks ของ project."""
        return list(self.client.tasks.list(project=project_id))

    def create_task(self, project_id: int, data: dict):
        """สร้าง task ใหม่ใน project."""
        return self.client.tasks.create(project=project_id, data=data)
