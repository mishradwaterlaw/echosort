"""
FaceFind End-to-End Integration Test
=====================================
Tests the full user journey:
  1.  Sign up / sign in → get JWT
  2.  Create an event              (POST /events)
  3.  Upload a photo               (POST /events/{id}/photos)
  4.  Poll embedding status        (GET  /events/{id}/photos?embedding_status=done)
  5.  Submit a selfie for matching (POST /events/{id}/match)
  6.  Poll for match results       (GET  /matches/{request_id})

USAGE
-----
    # From the facefind/api directory (with API running):
    pip install requests Pillow
    python tests/e2e_test.py

CONFIGURE
---------
Set the three constants below, or pass them as environment variables:
    E2E_API_URL       - base URL of the running FastAPI server (default: http://localhost:8000)
    E2E_SUPABASE_URL  - your Supabase project URL
    E2E_ANON_KEY      - your Supabase anon key (used only for sign-up/sign-in)
    E2E_TEST_EMAIL    - a real or throwaway test email
    E2E_TEST_PASSWORD - password for that account (min 6 chars)
"""

import io
import json
import os
import sys
import time

import requests
from PIL import Image

# ──────────────────────────────────────────────────────────────────────────────
# Config — override via environment variables or edit directly
# ──────────────────────────────────────────────────────────────────────────────
API_URL       = os.getenv("E2E_API_URL",       "http://localhost:8000")
SUPABASE_URL  = os.getenv("E2E_SUPABASE_URL",  "https://mtqdvxokombuvcyjyraa.supabase.co")
ANON_KEY      = os.getenv("E2E_ANON_KEY",      "")   # fill in your anon key
SERVICE_KEY   = os.getenv("E2E_SERVICE_KEY",   "")   # service_role key — used to create test user
TEST_EMAIL    = os.getenv("E2E_TEST_EMAIL",    "e2etest@example.com")
TEST_PASSWORD = os.getenv("E2E_TEST_PASSWORD", "testpassword123")

POLL_INTERVAL   = 5    # seconds between status checks
POLL_MAX_WAIT   = 120  # seconds before giving up on async steps

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def ok(label: str):
    print(f"  ✅  {label}")

def step(n: int, label: str):
    print(f"\n{'─'*60}")
    print(f"  STEP {n}: {label}")
    print(f"{'─'*60}")

def fail(label: str, detail: str = ""):
    print(f"\n  ❌  FAILED: {label}")
    if detail:
        print(f"      {detail}")
    sys.exit(1)

def assert_status(resp: requests.Response, expected: int, label: str):
    if resp.status_code != expected:
        fail(label, f"Expected {expected}, got {resp.status_code}\n      Body: {resp.text[:400]}")

def make_test_image(color=(255, 100, 100)) -> bytes:
    """Return a small JPEG as bytes (placeholder for a real photo)."""
    img = Image.new("RGB", (100, 100), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Step 0 – Authenticate with Supabase to get a JWT
# ──────────────────────────────────────────────────────────────────────────────
def authenticate() -> str:
    """
    Ensures the test user exists (using the admin API so email confirmation is skipped),
    then signs in as that user to get a JWT access_token.
    """
    admin_headers = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    # 1. Try to create the user via admin API (idempotent — 422 if already exists)
    create_resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=admin_headers,
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "email_confirm": True,  # bypass email confirmation
        },
    )
    if create_resp.status_code not in (200, 201, 422):
        fail("Create admin user", create_resp.text)

    # 2. Sign in with the password grant
    sign_in_resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if sign_in_resp.status_code != 200:
        fail("Sign-in", sign_in_resp.text)

    token = sign_in_resp.json().get("access_token")
    if not token:
        fail("Sign-in", "No access_token in response")

    ok(f"Authenticated as {TEST_EMAIL}")
    return token


# ──────────────────────────────────────────────────────────────────────────────
# Main test flow
# ──────────────────────────────────────────────────────────────────────────────
def run():
    print("\n" + "═"*60)
    print("  FaceFind – End-to-End Integration Test")
    print("═"*60)

    if not ANON_KEY or not SERVICE_KEY:
        fail("Config", "Set E2E_ANON_KEY and E2E_SERVICE_KEY environment variables.\n      "
             "ANON_KEY = your Supabase anon key\n      "
             "SERVICE_KEY = your Supabase service_role key")

    # ── Step 0: Auth ──────────────────────────────────────────────────────────
    step(0, "Authenticate with Supabase")
    token   = authenticate()
    headers = {"Authorization": f"Bearer {token}"}


    # ── Step 1: Create Event ──────────────────────────────────────────────────
    step(1, "Create Event  →  POST /events")
    resp = requests.post(
        f"{API_URL}/events",
        headers=headers,
        json={"name": "E2E Test Event", "description": "Automated test event"}
    )
    assert_status(resp, 201, "Create event")
    event = resp.json()
    event_id = event["id"]
    ok(f"Event created → id={event_id}")


    # ── Step 2: Upload Photo ──────────────────────────────────────────────────
    step(2, "Upload Photo  →  POST /events/{event_id}/photos")
    photo_bytes = make_test_image(color=(200, 150, 100))
    resp = requests.post(
        f"{API_URL}/events/{event_id}/photos",
        headers=headers,
        files=[("files", ("test_photo.jpg", photo_bytes, "image/jpeg"))]
    )
    assert_status(resp, 202, "Upload photo")
    upload_result = resp.json()
    accepted = upload_result["accepted"]
    photo_ids = upload_result["photo_ids"]
    if accepted < 1:
        fail("Upload photo", f"0 photos accepted. Skipped: {upload_result.get('skipped_files')}")
    ok(f"Photo accepted → photo_id={photo_ids[0]}")


    # ── Step 3: Poll Embedding Status ─────────────────────────────────────────
    step(3, f"Poll Embedding Status  →  GET /events/{event_id}/photos (up to {POLL_MAX_WAIT}s)")
    print(f"  ⏳  Waiting for Modal worker to process embedding…")
    deadline = time.time() + POLL_MAX_WAIT
    embedding_done = False
    while time.time() < deadline:
        resp = requests.get(
            f"{API_URL}/events/{event_id}/photos",
            headers=headers,
            params={"embedding_status": "done"}
        )
        assert_status(resp, 200, "Poll embedding status")
        data = resp.json()
        if data["total"] > 0:
            embedding_done = True
            break
        print(f"  ⏳  Not ready yet (total_done=0) — retrying in {POLL_INTERVAL}s…")
        time.sleep(POLL_INTERVAL)

    if not embedding_done:
        fail(
            "Embedding timeout",
            f"Photo embedding was not marked 'done' within {POLL_MAX_WAIT}s. "
            "Is the Modal worker running? Check Modal logs."
        )
    ok("Photo embedding complete")


    # ── Step 4: Submit Selfie for Matching ────────────────────────────────────
    step(4, "Submit Selfie  →  POST /events/{event_id}/match")
    selfie_bytes = make_test_image(color=(200, 150, 100))  # same colour = best chance of a match
    resp = requests.post(
        f"{API_URL}/events/{event_id}/match",
        headers=headers,
        files=[("selfie", ("selfie.jpg", selfie_bytes, "image/jpeg"))]
    )
    assert_status(resp, 202, "Submit selfie")
    match_request = resp.json()
    request_id = match_request["request_id"]
    ok(f"Match request queued → request_id={request_id}")


    # ── Step 5: Poll Match Results ────────────────────────────────────────────
    step(5, f"Poll Match Results  →  GET /matches/{request_id} (up to {POLL_MAX_WAIT}s)")
    print(f"  ⏳  Waiting for Modal worker to process match…")
    deadline = time.time() + POLL_MAX_WAIT
    match_done = False
    while time.time() < deadline:
        resp = requests.get(f"{API_URL}/matches/{request_id}", headers=headers)
        assert_status(resp, 200, "Poll match results")
        result = resp.json()
        if result["status"] == "done":
            match_done = True
            break
        if result["status"] == "failed":
            fail("Match processing failed", "Worker returned status=failed. Check Modal logs.")
        print(f"  ⏳  Status={result['status']} — retrying in {POLL_INTERVAL}s…")
        time.sleep(POLL_INTERVAL)

    if not match_done:
        fail(
            "Match timeout",
            f"Match was not completed within {POLL_MAX_WAIT}s. Is the Modal worker running?"
        )
    ok(f"Match complete → {len(result['photos'])} photo(s) returned")
    if result["photos"]:
        ok(f"First signed URL: {result['photos'][0]['signed_url'][:80]}…")


    # ── Done ──────────────────────────────────────────────────────────────────
    print("\n" + "═"*60)
    print("  ✅  ALL STEPS PASSED — End-to-end test complete!")
    print("═"*60 + "\n")


if __name__ == "__main__":
    run()
