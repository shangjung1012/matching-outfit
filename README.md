# Matching Outfit

Matching Outfit is an outfit recommendation and virtual try-on prototype. It combines a clothing catalog, user taste preferences, fashion-article knowledge, FashionCLIP similarity search, and an optional CatVTON service to recommend coordinated outfits from local catalog images.

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
   - Outfit memories: user-authored or confirmed preference sentences scoped by occasion, time, and situation.

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
  - CatVTON API: virtual try-on jobs
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
- Integration logic for FashionCLIP, OpenAI-backed LLM calls, text embeddings, and CatVTON.

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
- `try_on_jobs`: local record of CatVTON virtual try-on job status.
- `alembic_version`: migration bookkeeping.

## Recommendation Flow

```text
user input + personal profile + user preferences
  -> retrieve relevant fashion observations from DB
  -> LLM query planner considers fit, proportion, comfort, and audience context
  -> planner creates catalog search queries by garment zone without inserting body measurements into FashionCLIP queries
  -> FashionCLIP searches catalog images/text
  -> outfit ranker combines upper/lower/one-piece candidates
  -> hard rules filter invalid items
  -> relevant preference sentences guide query planning and the final aesthetic review
  -> optional aesthetic reviewer re-ranks shortlist
  -> frontend displays final outfits
```

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

Create `.env` in the project root when using OpenAI or CatVTON integrations:

```text
OPENAI_API_KEY=...
CATVTON_API_URL=...
CATVTON_API_KEY=...
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

Virtual try-on uses an external CatVTON API. The backend stores local job metadata in `try_on_jobs`, forwards person and clothing images to CatVTON, polls job status, and proxies the final result image when available.

Relevant settings:

```text
CATVTON_API_URL
CATVTON_API_KEY
```

## Development Notes

- `requirements.txt` contains runtime dependencies.
- `requirements-dev.txt` contains development and test dependencies.
- Tests live under `backend/tests/` and `catvton/tests/`; they are useful for development but are not required just to run the app.
- Alembic migrations run automatically when the backend container starts.
