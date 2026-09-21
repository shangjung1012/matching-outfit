# 潮會搭 | AI Personal Styling Platform

> **1st Place, Makalot Industrial Track, 2026 Meichu Hackathon**

潮會搭 is an AI-powered personal styling platform that turns natural-language requests, personal preferences, weather context, and fashion knowledge into coordinated outfit recommendations. It combines conversational requirement gathering, multimodal clothing retrieval, personalized ranking, wardrobe-based styling, and optional virtual try-on in one experience.

## Demo

[![Watch the 潮會搭 product demo](https://img.youtube.com/vi/9g0lomwAbMY/hqdefault.jpg)](https://youtu.be/9g0lomwAbMY)

[Watch the product demo on YouTube](https://youtu.be/9g0lomwAbMY)

_GitHub does not allow embedded YouTube players in README files. Click the preview image to watch the video._

## Product Overview

Finding an outfit is rarely just a product search. Users may care about the occasion, weather, budget, preferred silhouette, color palette, comfort, and items they already own. 潮會搭 gathers this context through a guided conversation and converts it into user-facing styling directions.

The recommendation pipeline then:

1. Interprets the user's occasion, style, constraints, and intended clothing audience.
2. Uses saved profile and preference data when the request does not provide enough context.
3. Retrieves visually and semantically relevant catalog items with FashionCLIP.
4. Builds complete outfit candidates and ranks them for compatibility and context fit.
5. Applies fashion knowledge and AI-assisted aesthetic review to the final selection.
6. Learns from confirmed preferences, favorites, and saved outfit combinations.

Users can also upload a photo of an existing top or bottom. The uploaded item remains fixed while the system searches for a matching counterpart, allowing the recommendation flow to begin with clothing the user already owns.

## Key Features

- **Conversational outfit discovery** — turns everyday language into structured styling requirements and outfit directions.
- **Personalized recommendations** — considers profile data, price limits, avoided attributes, saved preferences, and previous choices.
- **Style an existing item** — accepts a user-provided top or bottom and recommends complementary catalog pieces.
- **Fashion MBTI** — creates a shareable style profile and saves the result as a reusable preference.
- **Visual similarity search** — finds catalog items that resemble an uploaded clothing image.
- **Weather-aware styling** — incorporates location, date, temperature, and rain probability into outfit planning.
- **Fashion knowledge retrieval** — uses curated article observations as additional styling context.
- **Favorites and outfit memory** — stores individual products and complete outfit relationships.
- **Virtual try-on** — optionally submits person and garment images to a separate GPU inference service.

## Architecture

```text
Vue 3 + TypeScript frontend
            |
            | /api through the Vite proxy
            v
       FastAPI backend
            |
            +-- PostgreSQL + pgvector
            +-- FashionCLIP retrieval
            +-- OpenAI planning and review
            +-- Optional GPU try-on service
```

The root Docker Compose stack starts the frontend, backend, and PostgreSQL database. Database migrations run automatically when the backend starts. The GPU virtual try-on stack is separate and optional.

## Quick Start

### Requirements

- Docker Desktop
- Docker Compose
- An OpenAI API key for AI planning, knowledge extraction, embeddings, and aesthetic review

### 1. Configure the environment

Create a local environment file from the provided template:

```powershell
Copy-Item .env.example .env
```

Set at least the OpenAI API key in `.env`:

```env
OPENAI_API_KEY=your_api_key
```

Virtual try-on is optional. Leave these values empty when no GPU service is available:

```env
TRYON_API_URL=
TRYON_API_KEY=
```

### 2. Start the application

```powershell
docker compose up --build -d
```

Once the containers are ready, open:

- Frontend: http://localhost:5173
- API documentation: http://localhost:8000/docs
- API health check: http://localhost:8000/health

Check container status if a service is unavailable:

```powershell
docker compose ps
docker compose logs -f backend frontend
```

## Catalog Setup

Place the catalog CSV and product images under `data/`. Each CSV item ID should match its image filename.

```text
data/
  styles.csv
  images/
    1163.jpg
    1164.jpg
```

Import the catalog and build missing FashionCLIP image embeddings:

```powershell
docker compose exec backend python -m scripts.import_catalog `
  --csv /data/styles.csv `
  --image-dir /data/images `
  --default-price 1000

docker compose exec backend python -m scripts.build_embeddings
```

The first embedding run may take longer because the FashionCLIP model must be downloaded and cached.

## Common Commands

```powershell
# Start or rebuild the complete application
docker compose up --build -d

# Restart only the frontend
docker compose restart frontend

# Follow application logs
docker compose logs -f backend frontend

# Stop the application while preserving data
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete the PostgreSQL volume and all database state.

## Technology Stack

- **Frontend:** Vue 3, TypeScript, Vite
- **Backend:** FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL, pgvector
- **AI and retrieval:** OpenAI API, FashionCLIP
- **Infrastructure:** Docker Compose
- **Optional GPU pipeline:** FastFit and LHM++

## Virtual Try-On

Virtual try-on runs as a separate GPU service and is not started by the root Docker Compose configuration. The rest of the application remains available when `TRYON_API_URL` and `TRYON_API_KEY` are not configured.

FastFit and LHM++ source code, models, and weights include non-commercial or separately defined usage restrictions. Review the following files before deployment or redistribution:

- `gpu/tryon/LICENSE`
- `gpu/tryon/NOTICE`
- `gpu/tryon/UPSTREAM.md`
- `gpu/human3d/UPSTREAM.md`
