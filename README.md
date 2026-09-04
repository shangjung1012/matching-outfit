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
  - TryOn API: GPU-backed virtual try-on jobs
```

### Frontend

The frontend is a Vue 3 + Vite app. It provides catalog browsing, preference editing, recommendation flow, and virtual try-on screens.

Default URL:

```text
http://localhost:5173
```

### Backend

The backend is a FastAPI app. It owns:

- API routes for catalog listing, query planning, semantic search, recommendations, preferences, article knowledge status, and virtual try-on.
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
- `fashion_articles`: article metadata and extracted summary.
- `fashion_observations`: reusable outfit observations extracted from articles, with tags and text embeddings.
- `fashion_rules`: curated styling rules with conditions, recommendation text, source, weight, and active flag.
- `try_on_jobs`: local record of remote virtual try-on job status and selected reference types.
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

Virtual try-on uses the separate GPU service in `tryon/`. The root Compose stack intentionally does not build or launch it: deploy the service on an NVIDIA Linux host, then point the backend at its authenticated URL. The backend stores local job metadata in `try_on_jobs`, submits the images, polls the remote job, and proxies the result when it is ready.

Each job requires one person image and at least one of these five independent reference slots:

```text
upper, lower, overall, shoe, bag
```

Several references can be submitted together. `overall` cannot be combined with `upper` or `lower`; shoe and bag references remain compatible with either clothing arrangement. The frontend enforces these combinations, and both the backend and GPU service validate them again. JPEG, PNG, and WebP uploads are accepted up to 10 MiB and 20 megapixels per image.

### Deploy the GPU service

The service requires an NVIDIA CUDA GPU, a compatible driver, Docker Compose, and NVIDIA Container Toolkit/CDI support. On the GPU host:

```bash
cd tryon
cp .env.example .env
# Set the API key, MinIO credentials, and Cloudflare Tunnel token.
docker compose --profile tunnel up --build -d
docker compose logs -f tryon cloudflared
```

The TryOn API and MinIO object store are private to their Compose network;
neither publishes a host port, including the MinIO console. In the Cloudflare
Tunnel configuration, route the published hostname to the fixed origin
`http://tryon:9001`. Set the root
`TRYON_API_URL` to that hostname's HTTPS endpoint, and set root
`TRYON_API_KEY` to the exact same secret as `TRYON_API_KEY` in `tryon/.env`.
Leave both root values empty when the GPU service is unavailable; the rest of
Matching Outfit continues to run and the try-on screen reports the service as
unavailable.

The first API startup downloads `zhengchong/FastFit-MR-1024` plus the DWPose, DensePose, and SCHP trees from `zhengchong/Human-Toolkit`. They are cached in the `tryon_hf_cache` Docker volume, so later container starts reuse them. Job manifests and results use the `tryon_minio_data` volume. Input deletion is attempted after every inference; transient failures retain their object keys and are retried by the periodic cleanup worker. Job results and any remaining job objects expire after 24 hours. Ordinary `docker compose down` preserves both volumes; do not add `-v` unless you intentionally want to erase the model cache and stored jobs.

Inference uses a 768 x 1024 person canvas, five 384 x 512 reference slots in canonical order, 30 denoising steps, guidance scale 2.5, and seed 42. TF32 is enabled and mixed precision is fixed to `bf16` for the target GPU host.

### Usage restriction

The vendored FastFit model and inference materials are licensed only for non-commercial, non-production use. This prototype must remain developer-operated and must not be exposed as a production or customer-facing service. A developer must manually review every generated image for unlawful or infringing content before any display, transmission, or distribution. Read `tryon/LICENSE`, `tryon/NOTICE`, and `tryon/UPSTREAM.md` before deploying or distributing the service.

## Development Notes

- `requirements.txt` contains runtime dependencies.
- `requirements-dev.txt` contains development and test dependencies.
- Tests live under `backend/tests/` and `tryon/tests/`; they are useful for development but are not required just to run the app.
- Alembic migrations run automatically when the backend container starts.
