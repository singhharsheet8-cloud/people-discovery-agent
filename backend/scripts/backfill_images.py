"""
backfill_images.py — Download and permanently store all existing profile images.

Run after setting SUPABASE_URL and SUPABASE_SERVICE_KEY in .env:
    cd backend && python -m scripts.backfill_images
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg

from app.config import get_settings
from app.tools.image_storage import store_image_permanently

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_URL = "postgresql://postgres.fpnlljelpepsjeznobhl:REDACTED_DB_PASSWORD@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"


async def backfill():
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        return

    conn = await asyncpg.connect(DB_URL, ssl="require")

    rows = await conn.fetch(
        "SELECT id, name, image_url FROM persons WHERE image_url IS NOT NULL ORDER BY name"
    )
    logger.info(f"Found {len(rows)} persons with images to migrate")

    updated = 0
    skipped = 0
    failed = 0

    for row in rows:
        pid, name, url = row["id"], row["name"], row["image_url"]

        # Already stored in Supabase Storage — skip
        if "supabase.co/storage" in url:
            logger.info(f"  ✅ SKIP (already stored): {name}")
            skipped += 1
            continue

        logger.info(f"  ⬆  Uploading: {name} ({url[:60]}...)")
        permanent = await store_image_permanently(url, name)

        if permanent:
            await conn.execute(
                "UPDATE persons SET image_url=$1 WHERE id=$2", permanent, pid
            )
            logger.info(f"     → {permanent}")
            updated += 1
        else:
            logger.warning(f"     ✗ Upload failed, keeping original URL")
            failed += 1

    await conn.close()

    print(f"\nDone: {updated} uploaded, {skipped} already stored, {failed} failed")


if __name__ == "__main__":
    asyncio.run(backfill())
