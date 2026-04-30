# Migration: Azure Container Apps → Hugging Face Spaces + Vercel

Goal: move off paid Azure infrastructure to a fully **free** hosting setup.
- **Backend** (FastAPI + EasyOCR + Gemini) → Hugging Face Spaces (Docker SDK, free CPU)
- **Frontend** (`frontend/index.html`) → Vercel (Hobby tier)
- Final URLs:
  - API:  `https://sriny2131-medishield.hf.space`
  - Site: `https://<vercel-project>.vercel.app`

What I already configured in this repo (no action needed from you):
- `README.md` has HF Space frontmatter (`sdk: docker`, `app_port: 8000`).
- `frontend/index.html` reads `API_BASE` from a `<meta name="api-base">` tag pointing at the HF Space.
- `frontend/vercel.json` declares the static-site config.
- CORS in [src/api.py](src/api.py) already allows all origins (`allow_origins=["*"]`).

---

## Step 1 — Create the Hugging Face Space

1. Go to <https://huggingface.co/new-space>.
2. Settings:
   - **Owner**: `sriny2131`
   - **Space name**: `medishield`
   - **License**: MIT
   - **Space SDK**: **Docker** → **Blank** template
   - **Hardware**: CPU basic (free)
   - **Visibility**: Public
3. Click **Create Space**.

## Step 2 — Add the GOOGLE_API_KEY secret

In the Space → **Settings** → **Variables and secrets** → **New secret**:
- **Name**: `GOOGLE_API_KEY`
- **Value**: (paste your Gemini API key)

The Space rebuilds automatically when you save.

## Step 3 — Push your code to the Space

The Space is its own git repo. From this project root:

```bash
# Add the HF Space as a second remote
git remote add hf https://huggingface.co/spaces/sriny2131/medishield

# (if HF asks for auth, generate a write token at https://huggingface.co/settings/tokens
#  and use it as the password when git prompts)
git push hf main
```

The Space will pick up the Dockerfile, build the image (~5–8 min), and start. Watch progress in the Space's **Logs** tab. Once it says "Running", visit:

```
https://sriny2131-medishield.hf.space/health
```

Should return `{"status":"ok"}`.

## Step 4 — Deploy the frontend to Vercel

Two options. Pick one.

### Option A: Vercel CLI (fastest)

```bash
npm i -g vercel
cd frontend
vercel                  # first time: log in, link project — accept defaults
vercel --prod           # promote to production
```

When asked for the project root, accept `./` (you're already inside `frontend/`).

### Option B: Vercel Dashboard (Git-integrated)

1. Go to <https://vercel.com/new>.
2. Import the GitHub repo `sriny3/medishield-document-classifier`.
3. **Root Directory**: `frontend`
4. **Framework Preset**: `Other` (it's static HTML — no build step).
5. **Build Command**: leave blank.
6. **Output Directory**: `.` (the `frontend/` folder itself)
7. Deploy.

## Step 5 — Verify end-to-end

1. Open the Vercel URL in your browser.
2. Drag in 5–10 images, hit Classify.
3. Watch the rows flip waiting → processing → done.

If you see CORS errors in the browser console, the meta tag in `frontend/index.html` is wrong — confirm it points at your actual HF Space URL.

## Step 6 — (Optional) Tear down Azure to stop billing

```bash
bash infra/teardown.sh
```

This deletes the entire `medishield-rg` resource group. Irreversible.

---

## Caveats with the free tier

- **HF Space sleeps after ~48 h idle.** First request after sleep takes 30–60 s (cold start re-loads EasyOCR models). For demos, hit `/health` before the audience does to warm it up.
- **Shared CPU is slower than Azure.** Expect 4–6 s per LLM-stage classification vs ~2–3 s on Azure.
- **No persistent disk.** `_metrics` resets on every restart — same as Azure.
- **Vercel Hobby limits.** 100 GB bandwidth/month, no commercial use clause. Plenty for a portfolio demo.
- **Public Space = public Dockerfile.** Don't commit secrets; HF Secrets are injected as env vars at runtime, not visible in the repo.

## Rollback

If you tear down Azure and HF/Vercel break later:

```bash
bash infra/deploy.sh    # re-creates the Azure resource group from scratch
git push origin main    # CI deploys to it
```

The Azure side has not been deleted by this migration — only stopped paying for it (if you ran step 6).
