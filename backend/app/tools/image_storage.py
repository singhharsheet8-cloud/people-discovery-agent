"""
image_storage.py — Download profile images and store them permanently in
Supabase Storage so URLs never expire.

Public bucket: profile-images
Public URL pattern: {SUPABASE_URL}/storage/v1/object/public/profile-images/{filename}

Usage:
    from app.tools.image_storage import store_image_permanently
    permanent_url = await store_image_permanently(original_url, person_name)
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
import unicodedata

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BUCKET = "profile-images"

_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}


def _slug(name: str) -> str:
    """Convert a person name to a safe filename slug."""
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[^\w\s-]", "", name.lower())
    name = re.sub(r"[\s_-]+", "-", name).strip("-")
    return name or "person"


def _ext_from_content_type(content_type: str, url: str) -> str:
    """Derive a file extension from content-type or URL."""
    ct = content_type.split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/avif": ".avif",
    }
    if ct in mapping:
        return mapping[ct]
    # Fallback: guess from URL
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if ext in url.lower():
            return ext
    return ".jpg"


async def _ensure_bucket(client: httpx.AsyncClient, base: str, headers: dict) -> bool:
    """Create the public bucket if it doesn't exist. Returns True on success."""
    # Check if it already exists
    r = await client.get(f"{base}/storage/v1/bucket/{BUCKET}", headers=headers)
    if r.status_code == 200:
        return True

    # Create it
    r = await client.post(
        f"{base}/storage/v1/bucket",
        headers=headers,
        json={"id": BUCKET, "name": BUCKET, "public": True},
    )
    if r.status_code in (200, 201):
        logger.info(f"[storage] Created Supabase bucket '{BUCKET}'")
        return True

    logger.warning(f"[storage] Could not create bucket: {r.status_code} {r.text[:200]}")
    return False


async def store_image_permanently(
    url: str,
    person_name: str,
    *,
    timeout: float = 20.0,
) -> str | None:
    """
    Download the image at *url* and upload it to Supabase Storage.

    Returns the permanent public URL (supabase.co/storage/...) on success,
    or None if storage is not configured / download fails.

    The filename is deterministic:  <slug>-<sha8>.jpg  so re-running
    for the same person is idempotent (upsert overwrites existing file).
    """
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_service_key:
        # Storage not yet configured — return None gracefully, caller keeps original URL
        logger.debug("[storage] Supabase storage not configured, skipping upload")
        return None

    base = settings.supabase_url.rstrip("/")
    auth_headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key,
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        # 1. Ensure the bucket exists
        if not await _ensure_bucket(client, base, auth_headers):
            return None

        # 2. Download the image
        try:
            resp = await client.get(url, headers=_DOWNLOAD_HEADERS)
            resp.raise_for_status()
            image_bytes = resp.content
            content_type = resp.headers.get("content-type", "image/jpeg")
        except Exception as e:
            logger.warning(f"[storage] Failed to download image from {url[:80]}: {e}")
            return None

        if not image_bytes:
            return None

        # 3. Build a deterministic filename
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
        ext = _ext_from_content_type(content_type, url)
        slug = _slug(person_name)
        filename = f"{slug}-{url_hash}{ext}"

        # 4. Upload to Supabase Storage (upsert so re-runs are safe)
        upload_headers = {
            **auth_headers,
            "Content-Type": content_type,
            "x-upsert": "true",  # overwrite if exists
        }
        try:
            up = await client.post(
                f"{base}/storage/v1/object/{BUCKET}/{filename}",
                headers=upload_headers,
                content=image_bytes,
            )
            if up.status_code in (200, 201):
                permanent = f"{base}/storage/v1/object/public/{BUCKET}/{filename}"
                logger.info(f"[storage] Stored image for '{person_name}': {permanent}")
                return permanent
            else:
                logger.warning(
                    f"[storage] Upload failed for '{person_name}': "
                    f"{up.status_code} {up.text[:200]}"
                )
        except Exception as e:
            logger.warning(f"[storage] Upload error for '{person_name}': {e}")

    return None
