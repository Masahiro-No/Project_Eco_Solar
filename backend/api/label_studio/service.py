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

    def create_annotation(self, task_id: int, result: list[dict], ground_truth: bool = True):
        """บันทึก annotation สำหรับ task."""
        return self.client.annotations.create(id=task_id, result=result, ground_truth=ground_truth)

    def list_annotations(self, task_id: int) -> list:
        """คืนรายการ annotations ของ task."""
        return list(self.client.annotations.list(task=task_id))

    def get_task(self, task_id: int):
        """คืนข้อมูล task."""
        return self.client.tasks.get(id=str(task_id))

    def list_tasks_with_annotations(self, project_id: int) -> list:
        """คืน tasks ทั้งหมดของ project พร้อม annotations (ใช้หา label ที่มีอยู่แล้ว).

        ขอทีละ 1000 task: ค่าเริ่มต้นของ SDK แบ่งหน้าเล็ก ทำให้ 679 task ใช้ 24 วินาที (หน้าใหญ่ใช้ราว 10 วินาที)
        """
        return list(self.client.tasks.list(project=project_id, fields="all", page_size=1000))

    def update_task(self, task_id: int, data: dict):
        """แก้ data ของ task."""
        return self.client.tasks.update(id=str(task_id), data=data)

    def update_annotation(self, annotation_id: int, result: list[dict], ground_truth: bool = True):
        """แก้ result ของ annotation เดิม."""
        return self.client.annotations.update(id=annotation_id, result=result, ground_truth=ground_truth)

    def get_or_create_project(self, title: str, label_config: str):
        """คืน project ถ้ามีอยู่แล้ว หรือสร้างใหม่ถ้ายังไม่มี."""
        for p in self.list_projects():
            if p.title == title:
                return p
        return self.create_project(title=title, label_config=label_config)
