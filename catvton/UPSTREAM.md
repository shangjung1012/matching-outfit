# CatVTON runtime

This directory contains the minimum runtime code vendored from
[Zheng-Chong/CatVTON](https://github.com/Zheng-Chong/CatVTON) for the virtual
try-on service. The upstream code and model materials are licensed under
CC BY-NC-SA 4.0; see `LICENSE`.

The Gradio applications, datasets, evaluation scripts, examples, model weights,
input images, outputs, caches, and upstream Git metadata are intentionally not
included. Model checkpoints are downloaded to `HF_HOME` when the GPU service is
started for the first time.

## Standalone deployment

`docker-compose.yml` runs only the CatVTON API and its private MinIO instance.
It never connects to the Matching Outfit PostgreSQL database. Copy
`.env.example` to `.env`, replace every secret, and run `docker compose up
--build -d` on an NVIDIA Linux host.
