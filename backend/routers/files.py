"""File upload and download endpoints."""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from services.auth import get_current_user
from services.files import get_object, upload

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


@router.get("/object/{key:path}")
async def download_file(key: str):
    try:
        obj = get_object(key)
    except ValueError:
        raise HTTPException(status_code=400, detail="文件 key 无效")
    except Exception:
        raise HTTPException(status_code=404, detail="文件不存在")

    body = obj["Body"]
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
    }
    return StreamingResponse(
        body.iter_chunks(),
        media_type=obj.get("ContentType") or "application/octet-stream",
        headers=headers,
    )
