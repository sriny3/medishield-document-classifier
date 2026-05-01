# Hugging Face Spaces — Backend Deployment Steps

Single source of truth for deploying the FastAPI backend to a free
Hugging Face Space. Follow it top to bottom.

> Companion script: [infra/deploy_huggingface.py](infra/deploy_huggingface.py)
> does steps 3–6 in one shot. The earlier steps (token, secrets) cannot
> be automated — they are auth-gated to your HF account.

---

## Final URL

`https://sriny2131-medishield.hf.space`

`/health` should return `{"status":"ok"}` once the build finishes.

---

## Prerequisites

| What | How |
|---|---|
| HF account | <https://huggingface.co/join> — username `sriny2131` |
| HF write token | <https://huggingface.co/settings/tokens> → **New token** → role **Write**. Copy the `hf_…` string somewhere safe; you cannot view it again. |
| Gemini API key | <https://aistudio.google.com/app/apikey> — same key you used on Azure. |
| Local Python | Already installed (3.12). The script auto-imports `huggingface_hub` and `requests`. |

---

## Step 1 — Confirm the repo prep is in place

These files were committed in `cf16761`. Verify they exist:

```bash
grep -m1 "sdk: docker" README.md          # HF Space metadata
grep -m1 "api-base"   frontend/index.html # frontend reads URL from meta
ls infra/deploy_huggingface.py            # the deploy script
```

If any are missing, pull `main`.

## Step 2 — Install the HF SDK locally

```bash
pip install huggingface_hub requests
```

(Already installed in this environment — version 0.36.2.)

## Step 3 — Run the one-shot deploy

```bash
export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxx
export GOOGLE_API_KEY=AIzaSyxxxxxxxxxxxxxxxx
python infra/deploy_huggingface.py
```

What it does, in order:

1. **`create_repo`** — creates `sriny2131/medishield` as a Docker Space.
   `exist_ok=True`, so safe to re-run.
2. **`add_space_secret`** — injects `GOOGLE_API_KEY` as a Space secret
   (env var at runtime, not visible in the repo).
3. **`upload_folder`** — syncs the project into the Space's git repo,
   ignoring `.venv`, `dataset/`, images, tests. HF starts building the
   Dockerfile automatically on push.
4. **Health poll** — hits `/health` every 20 s until it returns 200 or
   15 minutes elapse. Cold builds with EasyOCR + PyTorch typically take
   6–10 min.

You'll see live progress; the script exits 0 once the Space is live.

## Step 4 — If the build fails

Open <https://huggingface.co/spaces/sriny2131/medishield/logs> and
scroll to the bottom. Common issues:

| Symptom | Cause | Fix |
|---|---|---|
| `easyocr` model download timeout | HF build network blip | Re-run the script — uploads are diff-only, so HF rebuilds with cached Docker layers. |
| `KeyError: 'GOOGLE_API_KEY'` at startup | Secret missing | Re-run the script (step 2 sets it again). |
| `Out of memory during pip install` | Free tier RAM limit hit during torch install | Already mitigated by the multi-stage Dockerfile — if you see this, upgrade to CPU upgrade tier ($0.03/hr) for the build window only, then downgrade. |
| Health probe times out at 15 min | Big PyTorch download still running | Re-run the script — second poll will pick up where the first left off. |

## Step 5 — Wire the frontend to the Space

The frontend already reads the Space URL from a meta tag set in
[frontend/index.html](frontend/index.html):

```html
<meta name="api-base" content="https://sriny2131-medishield.hf.space" />
```

If you change the Space name, update this and redeploy the frontend.

## Step 6 — Optional: tear down Azure

Once the Space is live and you've smoke-tested it:

```bash
bash infra/teardown.sh
```

This deletes the entire `medishield-rg` resource group and stops billing.

---

## Manual fallback (if the script can't run)

Everything the script does is also doable by hand:

```bash
# 3a. Create the Space
curl -X POST https://huggingface.co/api/repos/create \
  -H "Authorization: Bearer $HF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"medishield","organization":"sriny2131","type":"space","sdk":"docker"}'

# 3b. Add the secret (web UI only — no public REST endpoint for secrets)
# → https://huggingface.co/spaces/sriny2131/medishield/settings → Variables and secrets

# 3c. Push via git
git remote add hf https://huggingface.co/spaces/sriny2131/medishield
git push hf main
# (when prompted for password, paste your HF write token)
```

## What the script doesn't touch

- Your Azure deployment. It keeps running until you tear it down.
- Your local `.env`. The Space gets its key from HF Secrets, not from
  any local file.
- The Vercel frontend. Deploy that separately following step 4 of
  [MIGRATION_HF_VERCEL.md](MIGRATION_HF_VERCEL.md).
