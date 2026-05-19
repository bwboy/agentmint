"""File upload endpoint — multipart, 50 MB limit."""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException

from services.auth import get_current_user
from services.files import upload

router = APIRouter(prefix="/api/files", tags=["files"])

MAX_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    # Stream-check size: read in chunks, abort if oversize
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 50MB")

    # Wrap bytes in a BytesIO so boto3 can re-read
    import io
    stream = io.BytesIO(data)
    meta = upload(stream, file.filename or "upload.bin", file.content_type)
    meta["size_bytes"] = len(data)
    return meta
