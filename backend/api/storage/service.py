from minio import Minio
from minio.versioningconfig import ENABLED, OFF, VersioningConfig

from core.config import settings


def get_minio_client() -> Minio:
    """สร้าง MinIO client จาก settings."""
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=False,
    )


class StorageService:
    def __init__(self) -> None:
        self.client = get_minio_client()

    def list_buckets(self) -> list:
        """คืนรายชื่อ buckets ทั้งหมด."""
        return self.client.list_buckets()

    def create_bucket(self, bucket_name: str) -> None:
        """สร้าง bucket ใหม่ (ถ้ายังไม่มี)."""
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)

    def list_objects(self, bucket_name: str) -> list:
        """คืนรายชื่อ object ทั้งหมดใน bucket."""
        return list(self.client.list_objects(bucket_name, recursive=True))

    def upload_file(
        self,
        bucket_name: str,
        object_name: str,
        data,
        length: int,
        content_type: str = "application/octet-stream",
    ):
        """อัปโหลดไฟล์เข้า bucket."""
        return self.client.put_object(
            bucket_name, object_name, data, length, content_type=content_type, part_size=10*1024*1024
        )

    def download_file(self, bucket_name: str, object_name: str):
        """ดาวน์โหลดไฟล์จาก bucket — คืน urllib3 response."""
        return self.client.get_object(bucket_name, object_name)

    def set_versioning(self, bucket_name: str, enabled: bool) -> None:
        """เปิด/ปิด versioning ของ bucket."""
        status = ENABLED if enabled else OFF
        self.client.set_bucket_versioning(bucket_name, VersioningConfig(status))
