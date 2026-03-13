"""
backfill_images.py — Download and permanently store all existing profile images.

Uses curl for HTTP (avoids macOS Python SSL cert issues) and asyncpg for DB.

Run after setting SUPABASE_URL and SUPABASE_SERVICE_KEY in .env:
    cd backend && python -m scripts.backfill_images
"""
import asyncio
import hashlib
import logging
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_URL = "postgresql://postgres.fpnlljelpepsjeznobhl:MPBVi6rJB8P95aTc@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
SUPABASE_URL = "https://fpnlljelpepsjeznobhl.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZwbmxsamVscGVwc2plem5vYmhsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzM2MjE1NywiZXhwIjoyMDg4OTM4MTU3fQ.-NXsTaZ0K39lMX9h3ZDY6ETSgb1HG_lK6edzpP-R9fU"
BUCKET = "profile-images"

DOWNLOAD_HEADERS = [
    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "-H", "Accept: image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "-H", "Referer: https://www.google.com/",
]


def _slug(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[^\w\s-]", "", name.lower())
    name = re.sub(r"[\s_-]+", "-", name).strip("-")
    return name or "person"


def _filename(name: str, url: str, content_type: str = "") -> str:
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
    if "png" in content_type or url.endswith(".png"):
        ext = ".png"
    elif "webp" in content_type or "webp" in url:
        ext = ".webp"
    else:
        ext = ".jpg"
    return f"{_slug(name)}-{url_hash}{ext}"


def curl_download(url: str, dest: str) -> tuple[bool, str]:
    """Download URL to dest using curl. Returns (success, content_type)."""
    result = subprocess.run(
        ["curl", "-s", "-L", "-o", dest, "-w", "%{http_code}|%{content_type}", "--max-time", "20"]
        + DOWNLOAD_HEADERS
        + [url],
        capture_output=True, text=True
    )
    out = result.stdout.strip()
    parts = out.split("|", 1)
    http_code = parts[0] if parts else "0"
    content_type = parts[1] if len(parts) > 1 else "image/jpeg"

    if http_code == "200" and os.path.getsize(dest) > 0:
        return True, content_type
    return False, content_type


def curl_upload(filepath: str, filename: str, content_type: str) -> str | None:
    """Upload file to Supabase Storage. Returns permanent public URL or None."""
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{filename}"
    result = subprocess.run(
        [
            "curl", "-s", "-X", "POST", url,
            "-H", f"Authorization: Bearer {SERVICE_KEY}",
            "-H", f"apikey: {SERVICE_KEY}",
            "-H", f"Content-Type: {content_type}",
            "-H", "x-upsert: true",
            "-T", filepath,
        ],
        capture_output=True, text=True
    )
    if '"Key"' in result.stdout or '"id"' in result.stdout.lower():
        return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{filename}"
    logger.warning(f"    Upload failed: {result.stdout[:200]}")
    return None


async def backfill():
    conn = await asyncpg.connect(DB_URL, ssl="require")
    rows = await conn.fetch(
        "SELECT id, name, image_url FROM persons WHERE image_url IS NOT NULL ORDER BY name"
    )
    logger.info(f"Found {len(rows)} persons with images to migrate")

    updated = skipped = failed = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        for row in rows:
            pid, name, url = row["id"], row["name"], row["image_url"]

            if "supabase.co/storage" in url:
                logger.info(f"  ✅ SKIP (already in Supabase Storage): {name}")
                skipped += 1
                continue

            logger.info(f"  ⬇  Downloading: {name}")
            tmp_file = os.path.join(tmpdir, "img_tmp")

            ok, content_type = curl_download(url, tmp_file)
            if not ok:
                logger.warning(f"     ✗ Download failed for {name}")
                failed += 1
                continue

            size_kb = os.path.getsize(tmp_file) // 1024
            fname = _filename(name, url, content_type)
            logger.info(f"     ⬆  Uploading ({size_kb}KB) → {fname}")

            permanent = curl_upload(tmp_file, fname, content_type.split(";")[0].strip() or "image/jpeg")

            if permanent:
                await conn.execute("UPDATE persons SET image_url=$1 WHERE id=$2", permanent, pid)
                logger.info(f"     ✅ {permanent}")
                updated += 1
            else:
                logger.warning(f"     ✗ Upload failed, keeping original URL")
                failed += 1

    await conn.close()
    print(f"\n{'='*60}")
    print(f"Done: {updated} stored in Supabase, {skipped} already stored, {failed} failed")


if __name__ == "__main__":
    asyncio.run(backfill())
