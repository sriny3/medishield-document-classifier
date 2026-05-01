"""
One-shot deployment of the FastAPI backend to a Hugging Face Space.

Runs four steps in order, each idempotent:
  1. create_repo(...)              — create the Space if missing.
  2. add_space_secret(...)         — inject GOOGLE_API_KEY at runtime.
  3. upload_folder(...)            — push the repo contents into the Space.
  4. wait + GET /health            — block until the Space is healthy.

Usage:
  HF_TOKEN=hf_...  GOOGLE_API_KEY=AIza...  python infra/deploy_huggingface.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from huggingface_hub import HfApi, add_space_secret, create_repo, upload_folder
from huggingface_hub.utils import HfHubHTTPError

# ─────────────────────────── config ───────────────────────────
HF_USERNAME = "sriny2131"
SPACE_NAME = "medishield"
SPACE_ID = f"{HF_USERNAME}/{SPACE_NAME}"
SPACE_SDK = "docker"
SPACE_URL = f"https://{HF_USERNAME}-{SPACE_NAME}.hf.space"
HEALTH_URL = f"{SPACE_URL}/health"

REPO_ROOT = Path(__file__).resolve().parent.parent
# Files we don't want bloating the Space repo (HF has a 50 GB limit per
# repo but each push is bandwidth — keep it lean and identical to what
# Docker will COPY).
IGNORE = [
    ".venv/*",
    ".git/*",
    "__pycache__",
    "**/__pycache__/*",
    "*.pyc",
    "dataset/*",
    "diagrams/*",
    "*.png",
    "*.jpg",
    "*.jpeg",
    ".env",
    ".env.*",
    "tests/*",
    ".pytest_cache/*",
    ".vscode/*",
    "infra/deploy_huggingface.py",  # don't ship the deploy script itself
]


def die(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def step(n: int, msg: str) -> None:
    print(f"\n── Step {n}: {msg} ──")


def main() -> None:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        die("HF_TOKEN env var not set. Get one at https://huggingface.co/settings/tokens (scope: write).")
    google_key = os.environ.get("GOOGLE_API_KEY")
    if not google_key:
        die("GOOGLE_API_KEY env var not set. Needed so the Space can call Gemini at runtime.")

    api = HfApi(token=token)

    # 1. Create Space (idempotent — exist_ok=True returns existing repo).
    step(1, f"create_repo {SPACE_ID} (sdk={SPACE_SDK})")
    try:
        url = create_repo(
            repo_id=SPACE_ID,
            repo_type="space",
            space_sdk=SPACE_SDK,
            exist_ok=True,
            token=token,
        )
        print(f"   ✓ Space ready: {url}")
    except HfHubHTTPError as e:
        die(f"create_repo failed: {e}")

    # 2. Inject runtime secret. Adding the same secret again just updates
    #    the value — safe to re-run.
    step(2, "add_space_secret GOOGLE_API_KEY")
    try:
        add_space_secret(
            repo_id=SPACE_ID,
            key="GOOGLE_API_KEY",
            value=google_key,
            token=token,
        )
        print("   ✓ secret set (Space will rebuild on next push)")
    except HfHubHTTPError as e:
        die(f"add_space_secret failed: {e}")

    # 3. Upload the repo. We let HF compute hashes and only upload changed
    #    files, so re-runs are cheap.
    step(3, f"upload_folder from {REPO_ROOT}")
    try:
        upload_folder(
            repo_id=SPACE_ID,
            repo_type="space",
            folder_path=str(REPO_ROOT),
            ignore_patterns=IGNORE,
            commit_message="deploy: sync from local repo",
            token=token,
        )
        print("   ✓ repo synced. HF is now building the Docker image.")
    except HfHubHTTPError as e:
        die(f"upload_folder failed: {e}")

    # 4. Poll /health until it returns 200 or we hit a 15-minute timeout.
    #    Cold builds with EasyOCR + PyTorch typically take 6–10 min.
    step(4, f"poll {HEALTH_URL} until healthy (timeout 15 min)")
    deadline = time.time() + 15 * 60
    last_status = None
    while time.time() < deadline:
        try:
            r = requests.get(HEALTH_URL, timeout=10)
            if r.status_code == 200:
                print(f"\n✅ Space is live: {SPACE_URL}")
                print(f"   /health → {r.json()}")
                return
            if r.status_code != last_status:
                print(f"   /health → HTTP {r.status_code} (still building)")
                last_status = r.status_code
        except requests.RequestException:
            if last_status != "DNS":
                print("   DNS not resolving yet (Space still warming up)…")
                last_status = "DNS"
        time.sleep(20)

    die(
        "Space did not become healthy within 15 minutes. Check the build "
        f"logs at https://huggingface.co/spaces/{SPACE_ID}/logs"
    )


if __name__ == "__main__":
    main()
