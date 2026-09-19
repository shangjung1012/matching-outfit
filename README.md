# Matching Outfit

Matching Outfit is an outfit recommendation and virtual try-on prototype. It combines a clothing catalog, user taste preferences, fashion-article knowledge, FashionCLIP similarity search, and an optional external TryOn service to recommend coordinated outfits from local catalog images.

## What Goes In

The project has four main input sources:

1. **Catalog data**
   - `data/styles.csv`
   - `data/images/{id}.jpg`
   - The CSV row id should match the image filename, for example `styles.csv` id `1163` maps to `data/images/1163.jpg`.

2. **User request**
   - Free-text styling intent, such as occasion, weather, aesthetic, gender/audience, or constraints.
   - Sent through the frontend or API to produce search plans and outfit recommendations.

3. **User preferences**
   - Personal profile: gender, age, height, and weight.
   - Hard rules: price limits and attributes to avoid.
   - Outfit memories: user-authored or confirmed preference sentences scoped by normalized outfit context.
   - The user and Agent communicate in Traditional Chinese. Structured context tags are stored in English so they align with article observations.

4. **Fashion articles**
   - URL lists such as `data/article_urls.example.txt`.
   - Articles are collected into JSON, optionally extracted into reusable outfit observations with an LLM, then imported into PostgreSQL.

## Architecture

```text
frontend Vue app
  |
  | HTTP /api
  v
backend FastAPI
  |
  | SQLAlchemy
  v
PostgreSQL + pgvector

Optional external services:
  - OpenAI API: query planning, article extraction, aesthetic review, text embeddings
  - FashionCLIP model: image/text embedding search for catalog items
  - Unified GPU API: FastFit virtual try-on and optional LHM++ reconstruction
```

### Frontend

The frontend is a Vue 3 + Vite app. It provides catalog browsing, persistent item and outfit favorites, saved-pairing discovery, preference editing, recommendation flow, and virtual try-on screens.

Default URL:

```text
http://localhost:5173
```

### Backend

The backend is a FastAPI app. It owns:

- API routes for catalog listing, query planning, semantic search, recommendations, favorites, preferences, article knowledge status, and virtual try-on.
- SQLAlchemy models and Alembic migrations.
- Integration logic for FashionCLIP, OpenAI-backed LLM calls, text embeddings, and the TryOn API.

Default API docs:

```text
http://localhost:8000/docs
```

### Database

PostgreSQL stores catalog rows, user preferences, article-derived knowledge, and try-on jobs. The `pgvector` extension is used for embedding columns.

Main tables:

- `clothes`: imported catalog items, image paths, garment zones, price metadata, and FashionCLIP image embeddings.
- `user_hard_rules`: one row per user for personal profile data and hard filters such as price range and avoided colors or categories.
- `user_style_preferences`: context-scoped preference sentences, including user-authored entries and memories confirmed from liked outfits.
- `user_favorite_items`: per-user catalog bookmarks, including whether an item was saved directly or brought in by an outfit.
- `user_favorite_outfits` and `user_favorite_outfit_items`: saved outfit groups and their ordered item relationships, used to show every previously saved pairing in both directions.
- `fashion_articles`: article metadata and extracted summary.
- `fashion_observations`: reusable outfit observations extracted from articles, with tags and text embeddings.
- `fashion_rules`: curated styling rules with conditions, recommendation text, source, weight, and active flag.
- `try_on_jobs`: local record of remote virtual try-on job status and selected reference types.
- `human3d_jobs`: metadata linking a completed try-on job to its remote LHM++ reconstruction; binary artifacts stay in private object storage.
- `alembic_version`: migration bookkeeping.

## Recommendation Flow

```text
user input + personal profile + user preferences
  -> requirement collector chats in Chinese and summarizes the current conversation
  -> shared English context tags: occasions, seasons, times_of_day, climates, formalities, activities, styles
  -> LLM query planner considers the full request, profile, hard rules, and contextually similar outfit memories
  -> planner creates 5 upper-body, 5 lower-body, and 2 one-piece FashionCLIP queries without article knowledge
  -> FashionCLIP keeps the 10 most similar catalog items for each selected query
  -> hard rules permanently filter invalid catalog items
  -> results are deduplicated by item id and each garment zone keeps at most 40 items
  -> outfit ranker forms upper/lower pairs and keeps one-piece alternatives
  -> retrieve fashion observations using the same normalized outfit-context fields
  -> outfit agent reviews images, similar-context memories, and relevant observations
  -> only observations actually used for a final outfit become source links
  -> frontend displays re-ranked outfits and their cited article titles
```

Initial pairing uses `50%` average FashionCLIP relevance, `30%` basic color/usage
compatibility, and `20%` context fit. With five upper-body and five lower-body
queries, each zone can contribute up to 40 unique items after deduplication, producing
up to 1,600 upper/lower candidate pairs before shortlist and diversity selection.

Garment zones are normalized into:

```text
upper_body, lower_body, one_piece, accessory, other
```

## Article Knowledge Flow

Article ingestion is separate from catalog ingestion.

```text
data/article_urls.example.txt
  -> collect_articles
  -> data/articles/raw/*.json
  -> LLM extraction
  -> data/articles/records/*.json
  -> import_fashion_knowledge
  -> fashion_articles + fashion_observations
```

Collect only raw article JSON:

```powershell
docker compose run --rm backend python -m scripts.collect_articles `
  --url-file /data/article_urls.example.txt `
  --collect-only
```

Collect articles and extract observations:

```powershell
docker compose run --rm backend python -m scripts.collect_articles `
  --url-file /data/article_urls.example.txt
```

Import extracted records into PostgreSQL:

```powershell
docker compose run --rm backend python -m scripts.import_fashion_knowledge
```

## Catalog Flow

Place Kaggle-style catalog data here:

```text
data/
  styles.csv
  images/
    1163.jpg
    1164.jpg
```

Import catalog rows:

```powershell
docker compose exec backend python -m scripts.import_catalog `
  --csv /data/styles.csv `
  --image-dir /data/images `
  --default-price 1000 `
  --limit 100
```

Build missing FashionCLIP embeddings:

```powershell
docker compose exec backend python -m scripts.build_embeddings --limit 100
```

## Run Locally

Copy `.env.example` to `.env` in the project root and add credentials for the integrations you use:

```text
OPENAI_API_KEY=...
TRYON_API_URL=https://tryon.example.com
TRYON_API_KEY=...
```

Start the app stack:

```powershell
docker compose up --build
```

Services:

```text
Frontend:   http://localhost:5173
API docs:   http://localhost:8000/docs
API health: http://localhost:8000/health
Postgres:   localhost:5432
```

If the database schema changes or a fresh database is needed:

```powershell
docker compose down
docker compose up --build
```

Use `docker compose down -v` only when you intentionally want to delete the PostgreSQL volume.

## Virtual Try-On

Virtual try-on uses the separate GPU stack in `gpu/`. The root Compose stack intentionally does not build or launch it. The GPU gateway is the only public entry point: FastFit remains at `/v1/...`, while optional LHM++ routes live under `/human3d/v1/...`. The root app therefore needs only one GPU URL, `TRYON_API_URL`, and its shared `TRYON_API_KEY`.

Each job requires one person image and at least one of these five independent reference slots:

```text
upper, lower, overall, shoe, bag
```

Several references can be submitted together. `overall` cannot be combined with `upper` or `lower`; shoe and bag references remain compatible with either clothing arrangement. The frontend enforces these combinations, and both the backend and GPU service validate them again. JPEG, PNG, and WebP uploads are accepted up to 10 MiB and 20 megapixels per image.

### Deploy the GPU stack

The stack requires an NVIDIA CUDA GPU, compatible driver, Docker Compose, and NVIDIA Container Toolkit/CDI support. FastFit and Human3D use separate images because their Python/CUDA native dependencies differ, but one Compose file and gateway manage both.

```bash
cd gpu
cp .env.example .env
# Set TRYON_API_KEY, MinIO credentials, and optionally the tunnel token.
docker compose --profile human3d --profile tunnel up --build -d
docker compose logs -f gateway tryon human3d cloudflared
```

Omit `--profile human3d` for FastFit only. Omit `--profile tunnel` for local-only use; the gateway listens on `127.0.0.1:9001` by default. If a remote host must publish that port, set `GPU_GATEWAY_BIND_ADDRESS=0.0.0.0` and protect it with a firewall or private network.

The APIs and MinIO stores remain private to the Compose network. In Cloudflare Tunnel, route the hostname to `http://gateway:8080`. Configure the root app with:

```text
TRYON_API_URL=https://gpu.example.com
TRYON_API_KEY=<the exact value from gpu/.env>
```

There are no separate Human3D URL or key settings. Leave both TryOn values empty when the GPU stack is unavailable; the rest of Matching Outfit still starts. If only FastFit runs, normal try-on stays available and the UI reports 3D as unavailable.

The first FastFit startup downloads `zhengchong/FastFit-MR-1024` plus DWPose, DensePose, and SCHP assets. They are cached in `tryon_hf_cache`; job data uses `tryon_minio_data`. Inputs are deleted after inference and results expire after 24 hours. Ordinary `docker compose down` preserves volumes; do not add `-v` unless you intentionally want to erase model caches and jobs.

Inference uses a 768 x 1024 person canvas, five 384 x 512 reference slots in canonical order, 30 denoising steps, guidance scale 2.5, and seed 42. TF32 is enabled and mixed precision is fixed to `bf16` for the target GPU host.

### FastFit usage restriction

The vendored FastFit model and inference materials are licensed only for non-commercial, non-production use. This prototype must remain developer-operated and must not be exposed as a production or customer-facing service. A developer must manually review every generated image for unlawful or infringing content before any display, transmission, or distribution. Read `gpu/tryon/LICENSE`, `gpu/tryon/NOTICE`, and `gpu/tryon/UPSTREAM.md` before deploying or distributing the service.

## 3D Try-On View

The optional second stage is:

```text
FastFit result PNG
  -> LHM++ single-view reconstruction
  -> native 3D Gaussian Splat PLY
  -> interactive browser viewer
```

After FastFit succeeds, the UI offers `產生 3D View`. The backend fetches the existing result server-side, submits it to Human3D, stores only job metadata in PostgreSQL, and proxies status and artifacts. The browser never contacts the GPU service or MinIO directly.

Human3D accepts JPEG, PNG, or WebP up to 10 MiB and 20 megapixels. It automatically segments the person, preserves subject aspect ratio on LHM++'s 512-square input canvas, and calls the official Gaussian export path. A single worker processes reconstruction jobs sequentially. Inputs are removed after processing; PLY results and job metadata expire after `HUMAN3D_JOB_TTL_HOURS` (24 by default).

### Shared RTX 5080 behavior

Both model containers use the same RTX 5080. Their inference paths acquire the same cross-process file lock, so FastFit and LHM++ never run heavy inference concurrently. LHM++ also has a single-worker queue.

`GPU_RESIDENCY_MODE=auto` implements the 16 GB policy:

1. FastFit starts resident by default.
2. Human3D first attempts to load LHM++ alongside it.
3. The first reconstruction samples whole-device peak VRAM through NVML.
4. Both remain resident only if measured peak usage leaves at least `GPU_VRAM_SAFETY_MARGIN_GB` free (1.5 GiB by default).
5. An OOM or insufficient measured headroom switches that Human3D process to lazy mode: unload FastFit, release cached CUDA memory, load and run LHM++, unload LHM++, then reload FastFit before releasing the shared lock.

Normal FastFit-only requests never load LHM++ and pay no LHM++ loading cost. Set `GPU_RESIDENCY_MODE=switch` to force lazy switching, or `resident` only after validating safe peak use. `/human3d/health` reports requested/effective mode, device-wide measured peak, model state, CUDA capability, and startup errors. Completed jobs also report LHM++'s PyTorch peak allocation.

Upstream documents roughly 8 GB for LHM++ inference, but that is not a combined-residency guarantee. FastFit, CUDA contexts, other processes, and allocator fragmentation also consume VRAM. On a 16 GB card, rely on measured values; `auto` falls back to switching when the configured margin is not preserved.

### RTX 5080 / Blackwell runtime

The Human3D image uses Python 3.10, CUDA 12.8, PyTorch 2.8.0+cu128, torchvision 0.23.0+cu128, xFormers 0.0.32.post2, and gsplat 1.5.3. PointOps, PyTorch3D, and diff-gaussian-rasterization compile from pinned sources with `TORCH_CUDA_ARCH_LIST=12.0`. Startup fails clearly if CUDA or a required extension is unavailable; there is no CPU fallback. Full pins are in `gpu/human3d/UPSTREAM.md`.

The first Human3D startup downloads `LHMPP-700M-PixelShuffle` and segmentation weights into the persistent `human3d_model_cache` volume. Rebuilding the container does not erase that volume.

Check both APIs through the single gateway:

```bash
curl -H "X-API-Key: $TRYON_API_KEY" http://127.0.0.1:9001/health
curl -H "X-API-Key: $TRYON_API_KEY" http://127.0.0.1:9001/human3d/health
```

Run standalone reconstruction from `gpu/`:

```bash
mkdir -p samples/output
# Put the source image at gpu/samples/input.png.
docker compose --profile human3d run --rm \
  -v "$PWD/samples:/work" \
  human3d python3.10 single_inference.py \
  --image /work/input.png \
  --output /work/output
```

The command prints the CUDA device, input, output artifact, elapsed time, and peak GPU memory. It writes a genuine Gaussian Splat `result.ply`, not a triangle-mesh conversion.

### Browser renderer and limitation

`Human3DViewer.vue` lazily loads `@mkkellogg/gaussian-splats-3d` only when opening 3D. It downloads the proxied PLY, progressively loads and GPU-sorts it, and provides mouse/touch orbit, wheel/pinch zoom, camera reset, responsive sizing, loading/failure states, and WebGL/object-URL cleanup.

V1 reconstructs from one try-on image. Side, back, hidden limbs, and unseen garment details are inferred and may not match real clothing; this is not physically accurate garment simulation. The UI displays this caveat while 3D is active.

### LHM++ license

The service wraps official LHM++ source pinned in `gpu/human3d/UPSTREAM.md`; this project does not own or redistribute its checkpoint. Upstream source is Apache-2.0, while model weights are separately licensed CC BY-NC 4.0 and require attribution and non-commercial use. Review the upstream licenses before deployment or distribution.

## Development Notes

- `requirements.txt` contains runtime dependencies.
- `requirements-dev.txt` contains development and test dependencies.
- Tests live under `backend/tests/`, `frontend/tests/`, `gpu/tryon/tests/`, and `gpu/human3d/tests/`; they are useful for development but are not required just to run the app.
- Alembic migrations run automatically when the backend container starts.
