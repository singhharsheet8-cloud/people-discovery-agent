#!/usr/bin/env python3
"""
Audit and fix bad profile images using the /refresh-image API endpoint.

For each person:
  1. Download their image and check aspect ratio / dimensions
  2. If bad (landscape, too small, etc.) → call POST /persons/{id}/refresh-image
     which clears the old image and runs the full resolution waterfall

Run against live backend:
  BACKEND_URL=https://people-discovery-agent-production.up.railway.app python scripts/fix_images.py

Run against local:
  python scripts/fix_images.py
"""
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    print("WARNING: Pillow not installed — dimension checks disabled")
    HAS_PIL = False

MIN_DIMENSION = 100
MIN_ASPECT = 0.45
MAX_ASPECT = 1.65


async def check_image(url: str) -> tuple[bool, str]:
    """Return (is_good_headshot, reason)."""
    if not url:
        return False, "no url"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0"}) as c:
            r = await c.get(url)
            if r.status_code not in (200, 206):
                return False, f"http {r.status_code}"
            ct = r.headers.get("content-type", "")
            if not ct.startswith("image/"):
                return False, f"not image: {ct}"
            if not HAS_PIL:
                return True, "ok (no dim check)"
            img = Image.open(io.BytesIO(r.content))
            w, h = img.size
            aspect = w / h
            if w < MIN_DIMENSION or h < MIN_DIMENSION:
                return False, f"too small: {w}x{h}"
            if aspect < MIN_ASPECT or aspect > MAX_ASPECT:
                return False, f"bad aspect {aspect:.2f} ({w}x{h} — {'landscape/news photo' if aspect > 1.3 else 'very tall'})"
            return True, f"ok {w}x{h} aspect={aspect:.2f}"
    except Exception as e:
        return False, f"error: {e}"


async def login(backend_url: str) -> str:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{backend_url}/api/auth/login",
            json={"email": "admin@discovery.local", "password": "changeme123"},
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def get_persons(backend_url: str, token: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{backend_url}/api/persons",
            params={"page": 1, "per_page": 50},
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json().get("items", [])


async def refresh_image(backend_url: str, token: str, person_id: str) -> dict:
    """Call the refresh-image endpoint."""
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{backend_url}/api/persons/{person_id}/refresh-image",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()


async def main():
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
    print(f"Backend: {backend_url}\n")

    token = await login(backend_url)
    print("✓ Logged in\n")

    persons = await get_persons(backend_url, token)
    print(f"Found {len(persons)} persons\n")
    print("=" * 70)

    bad_count = 0
    fixed_count = 0
    still_bad = []

    for person in persons:
        name = person["name"]
        pid = person["id"]
        image_url = person.get("image_url") or ""

        print(f"\n👤 {name}")
        if not image_url:
            print("   (no image)")
            continue

        print(f"   URL: {image_url[:85]}")
        good, reason = await check_image(image_url)

        if good:
            print(f"   ✅ {reason}")
        else:
            print(f"   ❌ Bad: {reason}")
            bad_count += 1

            print(f"   🔄 Refreshing image...")
            try:
                result = await refresh_image(backend_url, token, pid)
                new_url = result.get("image_url")
                if new_url:
                    print(f"   ➡ New URL: {new_url[:85]}")
                    # Verify the new one
                    new_good, new_reason = await check_image(new_url)
                    if new_good:
                        print(f"   ✅ New image OK: {new_reason}")
                        fixed_count += 1
                    else:
                        print(f"   ⚠ New image still bad: {new_reason}")
                        still_bad.append((name, new_url, new_reason))
                else:
                    print(f"   ⚠ No image found by resolver")
                    still_bad.append((name, "", "not found"))
            except Exception as e:
                print(f"   ✗ Refresh failed: {e}")
                still_bad.append((name, image_url, str(e)))

    print("\n" + "=" * 70)
    print(f"\n📊 Summary")
    print(f"   Total persons: {len(persons)}")
    print(f"   Bad images found: {bad_count}")
    print(f"   Fixed: {fixed_count}")
    if still_bad:
        print(f"   Still problematic ({len(still_bad)}):")
        for n, u, r in still_bad:
            print(f"     • {n}: {r}")


if __name__ == "__main__":
    asyncio.run(main())
