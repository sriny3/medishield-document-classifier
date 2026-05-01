---
title: MediShield Document Classifier
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
license: mit
---

# MediShield AI Document Classifier

> Automatically classify scanned insurance documents — bills, KYC identity proofs, prescriptions, lab reports and more — using a three-stage pipeline: filename rules → OCR → Gemini LLM.

[![CI](https://github.com/sriny3/medishield-document-classifier/actions/workflows/ci.yml/badge.svg)](https://github.com/sriny3/medishield-document-classifier/actions/workflows/ci.yml)
[![Deploy](https://github.com/sriny3/medishield-document-classifier/actions/workflows/deploy.yml/badge.svg)](https://github.com/sriny3/medishield-document-classifier/actions/workflows/deploy.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-green)
![Tests](https://img.shields.io/badge/tests-117%20passing-brightgreen)

**🚀 Live demo:** https://sriny2131-medishield.hf.space (Hugging Face Spaces, free CPU)

---

## Table of Contents

- [Background](#background)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Classification Pipeline](#classification-pipeline)
- [Project Structure](#project-structure)
- [Quick Start (Local)](#quick-start-local)
- [Running with Docker](#running-with-docker)
- [API Reference](#api-reference)
- [Frontend UI](#frontend-ui)
- [Monitoring with LangSmith](#monitoring-with-langsmith)
- [Deploying to Azure](#deploying-to-azure)
- [Running Tests](#running-tests)
- [Environment Variables](#environment-variables)

---

## Background

MediShield Insurance processes thousands of scanned health insurance claims every month. Previously, a team of 12 operators manually reviewed every document — classifying prescriptions, bills, KYC identity proofs, lab reports and claim forms by hand. This caused:

- **48-hour backlogs** during peak periods
- **6–8% misclassification rate** causing downstream rework
- Skilled operators doing mechanical sorting work

This system automates the classification step, targeting ≥ 95% accuracy and < 5 second processing time per document.

---

## How It Works

Every uploaded image passes through a **three-stage pipeline**. Each stage can short-circuit so only documents that truly need AI processing reach the LLM:

| Stage | Trigger | Result | LLM used? |
|---|---|---|---|
| **Rules Engine** | Filename starts with `bill_` | `doc_type = bill` | ❌ No |
| **KYC OCR** | easyocr finds Aadhaar/PAN/Passport keywords | `doc_type = kyc` | ❌ No |
| **Gemini LLM** | Everything else | `doc_type = image` + sub-type | ✅ Yes |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Browser / Client                          │
│              Drag & Drop UI  ·  frontend/index.html              │
└────────────────────────────┬─────────────────────────────────────┘
                             │  POST /classify  (multipart)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│              FastAPI  ·  src/api.py  ·  Port 8000                │
│                                                                  │
│   asyncio.gather → runs all files concurrently in thread pool    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Classification Pipeline  (src/classifier.py) │    │
│  │                                                          │    │
│  │  ┌──────────────┐   bill_*   ┌──────────────────────┐   │    │
│  │  │ Rules Engine  │──────────▶│  doc_type = "bill"   │   │    │
│  │  │(src/rules_   │           │  method   = "rules"  │   │    │
│  │  │ engine.py)   │           └──────────────────────┘   │    │
│  │  └──────┬───────┘                                       │    │
│  │         │ others                                        │    │
│  │         ▼                                               │    │
│  │  ┌──────────────┐  KYC kw   ┌──────────────────────┐   │    │
│  │  │  KYC OCR     │──────────▶│  doc_type = "kyc"    │   │    │
│  │  │(easyocr)     │           │  method   = "ocr"    │   │    │
│  │  │(src/kyc_     │           └──────────────────────┘   │    │
│  │  │ detector.py) │                                       │    │
│  │  └──────┬───────┘                                       │    │
│  │         │ no KYC match                                  │    │
│  │         ▼                                               │    │
│  │  ┌──────────────┐           ┌──────────────────────┐   │    │
│  │  │  Gemini LLM  │──────────▶│  doc_type = "image"  │   │    │
│  │  │ gemma-4-31b  │           │  sub_type = category │   │    │
│  │  │(src/llm_     │           │  method   = "llm"    │   │    │
│  │  │ classifier   │           └──────────────────────┘   │    │
│  │  │ .py)         │                                       │    │
│  │  └──────────────┘                                       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │           Monitoring  ·  src/monitoring.py               │    │
│  │   @traceable spans · token counts · structured logs      │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────┬───────────────────────────────────────────────────┘
               │
     ┌─────────┴──────────┐
     ▼                    ▼
 LangSmith            Azure Monitor
 (traces · tokens     (container logs
  · latency)          · metrics)
```

---

## Classification Pipeline

### Stage 1 — Rules Engine (`src/rules_engine.py`)

Uses a compiled regex `^bill_` against the filename. Zero ML cost — runs in < 1 ms.

```
bill_innovh_01.png  →  doc_type=bill  method=rules  ✓ done
```

### Stage 2 — KYC OCR Detector (`src/kyc_detector.py`)

Runs `easyocr` on the image bytes and matches against 11 regex patterns:

| Pattern | Matches |
|---|---|
| `\baadhaar\b` | Aadhaar cards |
| `\buidai\b` | UIDAI-issued docs |
| `\bpan\b` | PAN cards |
| `\bpassport\b` | Passports |
| `\bgovt\.?\s+of\s+india\b` | Govt. of India docs |
| `\bdate\s+of\s+birth\b` | DOB field |
| `\bincome\s+tax\b` | Income tax dept |
| `\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b` | 12-digit Aadhaar number |
| `\b[A-Z]{5}[0-9]{4}[A-Z]\b` | PAN card format |

```
03ac1d4117.png (Aadhaar scan)  →  doc_type=kyc  method=ocr  ✓ done
```

### Stage 3 — Gemini LLM Classifier (`src/llm_classifier.py`)

Sends image bytes + a structured prompt to `gemma-4-31b-it`. Returns one of:

- `Patient Bills`
- `Claim Forms`
- `KYC Documents`
- `Medical Reports`
- `Prescriptions`
- `Unknown`

```
05a5de87a2.png  →  doc_type=image  sub_type=Medical Reports  method=llm
```

---

## Project Structure

```
multimodal-ai/
├── src/
│   ├── rules_engine.py      # Stage 1: filename regex rules
│   ├── kyc_detector.py      # Stage 2: easyocr + KYC keyword matching
│   ├── llm_classifier.py    # Stage 3: Gemini multimodal classification
│   ├── classifier.py        # Pipeline orchestrator (wires all 3 stages)
│   ├── api.py               # FastAPI server (POST /classify, GET /health)
│   └── monitoring.py        # LangSmith @traceable wrappers + token logging
├── tests/
│   ├── test_rules_engine.py     # 11 tests
│   ├── test_kyc_detector.py     # 21 tests
│   ├── test_llm_classifier.py   # 32 tests
│   ├── test_classifier.py       # 29 tests
│   ├── test_api.py              # 11 tests
│   └── test_monitoring.py       # 13 tests  (117 total)
├── frontend/
│   └── index.html           # Self-contained drag & drop UI
├── infra/
│   ├── deploy.sh            # Azure Container Apps one-shot deploy
│   └── teardown.sh          # Delete all Azure resources
├── .github/
│   └── workflows/
│       ├── ci.yml           # Run tests on every push / PR
│       └── deploy.yml       # Build → push → deploy on merge to main
├── Dockerfile               # Two-stage build (uv builder + slim runtime)
├── .dockerignore
├── pyproject.toml
├── .env.example
└── IMPLEMENTATION_PLAN.md
```

---

## Quick Start (Local)

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A [Google Gemini API key](https://aistudio.google.com/app/apikey)
- (Optional) A [LangSmith API key](https://smith.langchain.com/) for tracing

### 1. Clone and install

```bash
git clone https://github.com/sriny3/medishield-document-classifier.git
cd multimodal-ai
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY
```

### 3. Start the API server

```bash
.venv/Scripts/python -m uvicorn src.api:app --reload --port 8000
# Windows:  .venv\Scripts\python -m uvicorn src.api:app --reload
```

> First startup takes ~30 seconds while easyocr loads its OCR models into memory.

### 4. Open the UI

Serve the frontend (any static server works):

```bash
cd frontend
python -m http.server 3000
```

Open `http://localhost:3000` and drag images from the `dataset/` folder.

---

## Running with Docker

```bash
# Build (downloads easyocr models into the image — takes ~5 min first time)
docker build -t medishield-classifier:latest .

# Run
docker run -p 8000:8000 \
  -e GOOGLE_API_KEY=your-key \
  -e LANGCHAIN_TRACING_V2=true \
  -e LANGCHAIN_API_KEY=your-langsmith-key \
  -e LANGCHAIN_PROJECT=medishield-classification \
  medishield-classifier:latest

# Verify
curl http://localhost:8000/health
```

---

## API Reference

### `POST /classify`

Classify one or more scanned document images.

**Request:** `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `files` | `File[]` | One or more PNG / JPEG / WebP images |

**Response:** `200 OK` — JSON array, one object per file

```json
[
  {
    "filename": "bill_innovh_01.png",
    "doc_type": "bill",
    "sub_type": null,
    "method": "rules",
    "latency_ms": 7,
    "input_tokens": 0,
    "output_tokens": 0
  },
  {
    "filename": "03ac1d4117.png",
    "doc_type": "kyc",
    "sub_type": null,
    "method": "ocr",
    "latency_ms": 1240,
    "input_tokens": 0,
    "output_tokens": 0
  },
  {
    "filename": "05a5de87a2.png",
    "doc_type": "image",
    "sub_type": "Medical Reports",
    "method": "llm",
    "latency_ms": 3210,
    "input_tokens": 312,
    "output_tokens": 4
  }
]
```

| Field | Values |
|---|---|
| `doc_type` | `bill` · `kyc` · `image` |
| `sub_type` | `Patient Bills` · `Claim Forms` · `KYC Documents` · `Medical Reports` · `Prescriptions` · `Unknown` · `null` |
| `method` | `rules` · `ocr` · `llm` |

**Error responses:**

| Code | Reason |
|---|---|
| `422` | Unsupported MIME type (only PNG / JPEG / WebP accepted) |
| `500` | Gemini API error or internal failure |

---

### `GET /health`

Liveness probe.

```json
{ "status": "ok" }
```

---

### `GET /metrics`

In-memory counters since last restart.

```json
{
  "total_requests": 42,
  "total_documents": 189,
  "total_input_tokens": 58320,
  "total_output_tokens": 756,
  "by_method": { "rules": 80, "ocr": 35, "llm": 74 },
  "by_doc_type": { "bill": 80, "kyc": 35, "image": 74 }
}
```

> **Note:** With multiple uvicorn workers each worker has its own counter. Use a single worker locally (`--workers 1`) to see accurate totals, or wire up Prometheus/Redis for production aggregation.

---

### `GET /docs`

Interactive Swagger UI — auto-generated by FastAPI.

---

## Frontend UI

A self-contained single-file drag & drop interface at `frontend/index.html`.

**Features:**
- Drag & drop zone or click-to-browse for PNG / JPEG / WebP
- Thumbnail preview grid with per-file remove button
- Sends **all files in one batch** — server classifies concurrently so `bill_` files return in < 10 ms without waiting for OCR/LLM calls on other files
- Live progress bar and per-file status rows (queued → classifying → done)
- Color-coded result badges: **bill** (blue) · **kyc** (orange) · **image** (green)
- Summary bar: counts per type + average latency
- All controls disabled during processing (no accidental re-submit)

---

## Monitoring with LangSmith

Every classification run emits a nested trace to [LangSmith](https://smith.langchain.com/):

```
classify-document  (chain)
  ├── rules-engine   (tool)   filename, doc_type, send_to_llm
  ├── kyc-ocr        (tool)   ocr_text_length, doc_type
  └── llm-classify   (llm)    sub_type, input_tokens, output_tokens
```

Token usage, latency, and inputs/outputs are visible per run in the LangSmith dashboard. Tracing is a **no-op** when `LANGCHAIN_TRACING_V2` is not set — safe for local dev and CI.

**Enable tracing:**

```bash
# .env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__your_key
LANGCHAIN_PROJECT=medishield-classification
```

---

## Deploying to Azure

### One-shot deploy (first time)

```bash
az login
chmod +x infra/deploy.sh infra/teardown.sh
./infra/deploy.sh
```

The script provisions:

| Resource | Purpose |
|---|---|
| Resource Group `medishield-rg` | Container for all resources |
| Azure Container Registry | Private Docker registry |
| Log Analytics Workspace | Container log ingestion |
| Container Apps Environment | Serverless container runtime |
| Container App | The running classifier (0.5 vCPU / 2 GB RAM, min 1 replica) |

Secrets (`GOOGLE_API_KEY`, `LANGCHAIN_API_KEY`) are injected via Container Apps secret references — never stored as plain env vars.

### CI/CD (automated on every merge to `main`)

`.github/workflows/deploy.yml` runs on every push to `main`:

1. ✅ Full test suite must pass
2. `az acr build` — builds image in Azure (no local Docker needed)
3. `az containerapp update` — rolling deploy, zero downtime
4. Smoke tests `/health` on the live URL

**GitHub secrets required:**

| Secret | How to get it |
|---|---|
| `AZURE_CLIENT_ID` | `az ad sp create-for-rbac --role contributor` |
| `AZURE_TENANT_ID` | Same command output |
| `AZURE_SUBSCRIPTION_ID` | `az account show --query id` |

### Teardown

```bash
./infra/teardown.sh
```

---

## Running Tests

```bash
# All 117 tests
.venv/Scripts/python -m pytest tests/ -v

# Single module
.venv/Scripts/python -m pytest tests/test_rules_engine.py -v

# With coverage
.venv/Scripts/python -m pytest tests/ --cov=src --cov-report=term-missing
```

| Module | Tests | What's covered |
|---|---|---|
| `test_rules_engine` | 11 | Regex matching, case sensitivity, full paths |
| `test_kyc_detector` | 21 | 8 KYC patterns, 5 non-KYC, mocked easyocr |
| `test_llm_classifier` | 32 | All 6 categories, token capture, prompt structure |
| `test_classifier` | 29 | Pipeline short-circuits, stage ordering, dataset scan |
| `test_api` | 11 | Endpoints, MIME validation, metrics, multi-file |
| `test_monitoring` | 13 | Trace output, token extraction, pipeline instrumentation |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | ✅ Yes | Gemini API key from Google AI Studio |
| `LANGCHAIN_TRACING_V2` | Optional | Set to `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | Optional | LangSmith API key |
| `LANGCHAIN_PROJECT` | Optional | LangSmith project name (default: `medishield-classification`) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + uvicorn |
| OCR | easyocr (CPU, English) |
| LLM | Google Gemini `gemma-4-31b-it` via `google-genai` |
| Monitoring | LangSmith (`@traceable`) |
| Packaging | uv + pyproject.toml |
| Container | Docker (two-stage, python:3.12-slim) |
| Cloud | Azure Container Apps + ACR + Log Analytics |
| CI/CD | GitHub Actions |
| Tests | pytest (117 tests, 0 live API calls) |
