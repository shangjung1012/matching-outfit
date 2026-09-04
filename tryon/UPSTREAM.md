# FastFit runtime

This directory contains the minimum runtime code vendored from
[Zheng-Chong/FastFit](https://github.com/Zheng-Chong/FastFit) at commit
`9c96fc019d71a52a01285b1a4b06450cb4826677`. Only the upstream `module/` and
`parse_utils/` trees are included under `fastfit/`.

The FastFit code and model materials are licensed under the FastFit
Non-Commercial License v1.0.0; see `LICENSE`. The upstream demo, datasets,
evaluation scripts, examples, model weights, caches, and Git metadata are not
included. Model checkpoints are downloaded through the Hugging Face cache in
`HF_HOME` when the GPU service starts for the first time.

The FastFit Model is licensed by LavieAI under the FastFit Non-Commercial
License. Copyright LavieAI. IN NO EVENT SHALL LAVIEAI BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH USE OF THIS MODEL.

## Standalone deployment

`docker-compose.yml` runs only the FastFit try-on API and its private MinIO
instance. It never connects to the Matching Outfit PostgreSQL database. Copy
`.env.example` to `.env`, replace every secret, and run `docker compose up
--build -d` on an NVIDIA Linux host.
