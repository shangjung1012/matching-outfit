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

The minimal DWPose inference and drawing runtime under
`fastfit/vendor/easy_dwpose/` is vendored from Easy DWPose 1.0.2. It retains
the upstream Apache License 2.0 at `fastfit/vendor/easy_dwpose/LICENSE`.
Unrelated demo and integration modules are omitted; the integration changes
only the package/import path. This avoids installing Easy DWPose's legacy,
mutually incompatible dependency pins while preserving the CPU ONNX Runtime
path used by this service.

The FastFit Model is licensed by LavieAI under the FastFit Non-Commercial
License. Copyright LavieAI. IN NO EVENT SHALL LAVIEAI BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH USE OF THIS MODEL.

## Deployment

FastFit is built as its own image but is orchestrated with the optional LHM++
service by `gpu/docker-compose.yml`. Both services are isolated from the
Matching Outfit PostgreSQL database and share only the GPU inference lock and
the authenticated gateway. See the root README for exact commands.
