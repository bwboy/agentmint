from io import BytesIO


def test_minio_upload_uses_public_endpoint_for_browser_urls(monkeypatch):
    from config import settings
    from services import files

    class FakeS3:
        def head_bucket(self, Bucket):
            return None

        def upload_fileobj(self, stream, bucket, key, ExtraArgs=None):
            assert stream.read() == b"image-bytes"
            assert bucket == "agentmint-files"
            assert ExtraArgs == {"ContentType": "image/png"}

    monkeypatch.setattr(settings, "file_store", "minio")
    monkeypatch.setattr(settings, "minio_endpoint", "http://minio:9000")
    monkeypatch.setattr(settings, "minio_public_endpoint", "http://localhost:9000")
    monkeypatch.setattr(settings, "minio_bucket", "agentmint-files")
    monkeypatch.setattr(files, "_client", lambda: FakeS3())
    monkeypatch.setattr(files.uuid, "uuid4", lambda: type("UUIDStub", (), {"hex": "abc123def456"})())

    meta = files.upload(BytesIO(b"image-bytes"), "screen.png", "image/png")

    assert meta["url"].startswith("http://localhost:9000/agentmint-files/uploads/")
    assert "http://minio:9000" not in meta["url"]
