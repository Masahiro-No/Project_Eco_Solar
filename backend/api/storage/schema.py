from datetime import datetime

from pydantic import BaseModel


class CreateBucketRequest(BaseModel):
    bucket_name: str


class ObjectResponse(BaseModel):
    name: str
    size: int
    last_modified: datetime | None = None


class BucketResponse(BaseModel):
    name: str
    creation_date: datetime | None = None
    objects: list[ObjectResponse] = []


class UploadResponse(BaseModel):
    bucket_name: str
    object_name: str
    etag: str
    version_id: str | None = None


class VersioningRequest(BaseModel):
    enabled: bool
