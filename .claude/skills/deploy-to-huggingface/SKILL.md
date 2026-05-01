---
name: deploy-to-huggingface
description: Deploys a FastAPI Docker backend to a Hugging Face Space — creates the Space (idempotent), injects GOOGLE_API_KEY as a runtime secret, uploads the repo, and polls /health until the Space is live. Use when the user says "deploy to hugging face", "push to HF Spaces", "host the backend on HF", or asks to migrate a containerized FastAPI app to HF's free tier. Reads HF_TOKEN, HF_USERNAME, HF_SPACE_NAME, and GOOGLE_API_KEY from .env. Requires a Dockerfile at the repo root and HF Space metadata in README.md frontmatter.
---

# Deploy to Hugging Face Spaces

Use this skill to push a FastAPI/Docker backend in the current repository to a free Hugging Face Space.

## Prerequisites — verify before running

1. **`.env` contains the four required keys.** Check with:
   ```bash
   grep -E "^(HF_TOKEN|HF_USERNAME|HF_SPACE_NAME|GOOGLE_API_KEY)=" .env
   ```
   If any is missing, ask the user for it. Do NOT proceed with placeholder values.

2. **`README.md` has HF Space frontmatter** at the top:
   ```yaml
   ---
   title: <Project name>
   sdk: docker
   app_port: 8000   # match the EXPOSE in Dockerfile
   ---
   ```
   If missing, prepend it. Without this, HF treats the Space as a Gradio app and the build will fail.

3. **`Dockerfile` exists at the repo root** and the FastAPI app listens on `0.0.0.0:<app_port>`. Default in this project is 8000.

4. **`infra/deploy_huggingface.py` exists and `huggingface_hub` is installed.**
   ```bash
   pip install huggingface_hub python-dotenv requests
   ```

## How to run

```bash
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 PYTHONUNBUFFERED=1 python -u infra/deploy_huggingface.py
```

The three env vars matter on Windows:
- `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` — without these, Python's default `cp1252` codec crashes on the `──` step banners with `UnicodeEncodeError`.
- `PYTHONUNBUFFERED=1` (and `python -u`) — without these, stdout is block-buffered when redirected, so the Monitor sees nothing for ~6–10 min until the Docker build finishes. Use both belt-and-braces; either alone has been observed to silently buffer.

## Run the script in the background and stream progress

The script does four things, then polls `/health` for up to 15 minutes:

```bash
python -u infra/deploy_huggingface.py   # use Bash with run_in_background:true
```

Then arm a Monitor on its output file with this filter:

```bash
tail -f <output-file> | grep -E --line-buffered "Step|Space ready|secret set|repo synced|HTTP|DNS|Space is live|Traceback|Error|✅|✓|❌"
```

Expected event sequence:
1. `Step 1: create_repo …` → `✓ Space ready: https://huggingface.co/spaces/<user>/<space>`
2. `Step 2: add_space_secret GOOGLE_API_KEY` → `✓ secret set`
3. `Step 3: upload_folder …` → `✓ repo synced. HF is now building the Docker image.`
4. `Step 4: poll … /health until healthy` → `DNS not resolving yet …` (cold start) → eventually `✅ Space is live: https://<user>-<space>.hf.space`

Total wall-clock: typically 6–10 minutes from upload to first 200.

## Verifying success

```bash
curl -fsS https://<HF_USERNAME>-<HF_SPACE_NAME>.hf.space/health
# Expected: {"status":"ok"}
```

Mark the deploy complete only after this returns 200. Do not trust the script's exit code in isolation.

## Known failure modes and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `UnicodeEncodeError: 'charmap' codec can't encode characters` | Windows cp1252 stdout | Set `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` before the command. |
| Output file stays at 0 bytes for minutes | Block-buffered stdout when redirected | Add `PYTHONUNBUFFERED=1` and use `python -u`. |
| HfHubHTTPError 401 on `create_repo` | HF token has wrong scope | Generate a token with **Write** role at <https://huggingface.co/settings/tokens>. |
| Space build fails: `KeyError: 'GOOGLE_API_KEY'` at startup | Secret not injected yet | Re-run the script — `add_space_secret` is idempotent. |
| `/health` 404 even after 15-min build | Wrong `app_port` in README frontmatter | Match `EXPOSE` in Dockerfile (8000 for this project). |
| Build OOMs during `pip install torch` | HF free tier RAM ceiling | Multi-stage Dockerfile already mitigates; if it still fails, temporarily upgrade Hardware to "CPU upgrade", build once, then downgrade. |

## What the script does NOT do

- Does not tear down Azure. Run `bash infra/teardown.sh` separately if migrating off paid infra.
- Does not commit to GitHub. Run `git add . && git commit && git push` separately to keep GitHub in sync (HF Spaces have their own git history).

## Frontend note

The Dockerfile bundles `frontend/index.html` into the image and FastAPI
serves it at `/`, so the same Space URL hosts both the API and the UI.
No separate frontend deploy is needed.

## After successful deploy

1. Update [HUGGINGFACE_DEPLOYMENT.md](../../../HUGGINGFACE_DEPLOYMENT.md) "Run log" table with the actual outcomes — preserves a record for the next time someone redeploys.
2. Remind the user to rotate `HF_TOKEN` and `GOOGLE_API_KEY` if they were ever pasted into a chat or shared in a screen recording. The chat transcript persists.
3. Smoke test the live URL: visit `https://<user>-<space>.hf.space/`, upload images, confirm the streaming UI works.

## File map for this skill

- [`infra/deploy_huggingface.py`](../../../infra/deploy_huggingface.py) — the actual deployment script.
- [`HUGGINGFACE_DEPLOYMENT.md`](../../../HUGGINGFACE_DEPLOYMENT.md) — long-form steps doc with token-generation instructions.
- [`SKILL_CREATION.md`](../../../SKILL_CREATION.md) — explanation of how this skill was built and how to author similar skills.
