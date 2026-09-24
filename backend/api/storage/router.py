from fastapi import APIRouter, status

from api.storage.controller import create_bucket, download_file, list_buckets, set_versioning, upload_file
from api.storage.schema import BucketResponse, UploadResponse

router = APIRouter(prefix="/storage", tags=["storage"])
router.add_api_route("/buckets", list_buckets, methods=["GET"], response_model=list[BucketResponse], status_code=status.HTTP_200_OK)
router.add_api_route("/buckets", create_bucket, methods=["POST"], status_code=status.HTTP_201_CREATED)
router.add_api_route("/upload", upload_file, methods=["POST"], response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
router.add_api_route("/download/{bucket_name}/{object_name}", download_file, methods=["GET"], status_code=status.HTTP_200_OK)
router.add_api_route("/buckets/{bucket_name}/versioning", set_versioning, methods=["PUT"], status_code=status.HTTP_200_OK)
