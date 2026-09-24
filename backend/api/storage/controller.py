from fastapi import Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from api.auth.model import User
from api.auth.service import get_current_user
from api.storage.schema import BucketResponse, CreateBucketRequest, UploadResponse, VersioningRequest
from api.storage.service import StorageService


async def list_buckets(
    _: User = Depends(get_current_user),
) -> list[BucketResponse]:
    svc = StorageService()
    buckets = svc.list_buckets()
    result = []
    for b in buckets:
        try:
            objs = svc.list_objects(b.name)
            obj_list = [{"name": o.object_name, "size": o.size, "last_modified": o.last_modified} for o in objs]
        except Exception:
            obj_list = []
        result.append(BucketResponse(name=b.name, creation_date=b.creation_date, objects=obj_list))
    return result


async def create_bucket(
    payload: CreateBucketRequest,
    _: User = Depends(get_current_user),
) -> dict:
    svc = StorageService()
    try:
        svc.create_bucket(payload.bucket_name)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return {"detail": f"Bucket '{payload.bucket_name}' created successfully"}


async def upload_file(
    bucket_name: str = Form(...),
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
) -> UploadResponse:
    svc = StorageService()
    try:
        result = svc.upload_file(
            bucket_name=bucket_name,
            object_name=file.filename,
            data=file.file,
            length=-1,  # unknown length, MinIO จะอ่าน stream ทั้งหมด
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return UploadResponse(
        bucket_name=result.bucket_name,
        object_name=result.object_name,
        etag=result.etag,
        version_id=result.version_id,
    )


async def download_file(
    bucket_name: str,
    object_name: str,
    _: User = Depends(get_current_user),
):
    svc = StorageService()
    try:
        response = svc.download_file(bucket_name, object_name)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    return StreamingResponse(
        response,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={object_name}"},
    )


async def set_versioning(
    bucket_name: str,
    payload: VersioningRequest,
    _: User = Depends(get_current_user),
) -> dict:
    svc = StorageService()
    try:
        svc.set_versioning(bucket_name, payload.enabled)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    state = "enabled" if payload.enabled else "disabled"
    return {"detail": f"Versioning {state} for bucket '{bucket_name}'"}
