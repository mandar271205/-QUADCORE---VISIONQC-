"""
Supabase Storage service.
Handles file uploads for originals, heatmaps, and reference images.
"""
import asyncio
import threading
import uuid
from datetime import datetime
from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class SupabaseStorageService:
    """Manages file uploads to Supabase Storage."""

    def __init__(self):
        self._client = None
        self._client_lock = threading.Lock()

    def _get_client(self):
        with self._client_lock:
            if self._client is None:
                from supabase import create_client
                self._client = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_SERVICE_ROLE_KEY,
                )
        return self._client

    def is_available(self) -> bool:
        return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)

    def _get_path(self, folder: str, filename: str) -> str:
        now = datetime.utcnow()
        return f"{folder}/{now.year}/{now.month:02d}/{filename}"

    async def upload_original(
        self,
        image_bytes: bytes,
        inspection_id: str,
    ) -> str:
        """Upload original inspection image. Returns public URL."""
        filename = f"{inspection_id}.jpg"
        path = self._get_path("originals", filename)
        return await self._upload(image_bytes, path, "image/jpeg")

    async def upload_heatmap(
        self,
        heatmap_bytes: bytes,
        inspection_id: str,
    ) -> str:
        """Upload heatmap PNG. Returns public URL."""
        filename = f"{inspection_id}.png"
        path = self._get_path("heatmaps", filename)
        return await self._upload(heatmap_bytes, path, "image/png")

    async def upload_reference_image(
        self,
        image_bytes: bytes,
        product_id: str,
    ) -> str:
        """Upload product reference image. Returns public URL."""
        file_id = str(uuid.uuid4())
        path = f"reference-images/{product_id}/{file_id}.jpg"
        return await self._upload(image_bytes, path, "image/jpeg")

    async def _upload(
        self,
        data: bytes,
        path: str,
        content_type: str,
    ) -> str:
        """Upload bytes to Supabase Storage. Returns public URL."""
        if not self.is_available():
            logger.info("Supabase Storage not configured - returning local base64 data URI")
            import base64
            b64_data = base64.b64encode(data).decode('utf-8')
            return f"data:{content_type};base64,{b64_data}"

        try:
            import asyncio
            client = await asyncio.to_thread(self._get_client)
            bucket = settings.SUPABASE_STORAGE_BUCKET

            def _do_upload():
                return client.storage.from_(bucket).upload(
                    path=path,
                    file=data,
                    file_options={"content-type": content_type, "upsert": "true"},
                )

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _do_upload)

            # Build public URL
            public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"
            logger.debug(f"[Storage] Uploaded: {path}")
            return public_url

        except Exception as e:
            logger.error(f"[Storage] Upload failed for {path}: {e}")
            logger.info("Falling back to base64 data URI so workflow succeeds without storage error")
            import base64
            b64_data = base64.b64encode(data).decode('utf-8')
            return f"data:{content_type};base64,{b64_data}"

    async def delete_file(self, path: str) -> bool:
        """Delete a file from storage."""
        if not self.is_available():
            return True
        try:
            import asyncio
            client = await asyncio.to_thread(self._get_client)
            bucket = settings.SUPABASE_STORAGE_BUCKET

            def _do_delete():
                return client.storage.from_(bucket).remove([path])

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _do_delete)
            return True
        except Exception as e:
            logger.error(f"[Storage] Delete failed for {path}: {e}")
            return False


async def check_storage_health() -> bool:
    """Check if Supabase Storage is reachable."""
    try:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            return False
        # List buckets as a health check
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: storage_service._get_client().storage.list_buckets())
        return True
    except Exception as e:
        logger.error(f"[Storage] Health check failed: {e}")
        return False


# Singleton instance
storage_service = SupabaseStorageService()
