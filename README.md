# Matching Outfit

以自然語言拆解穿搭需求，使用 FashionCLIP 做文字對圖片搜尋，再將候選衣服組成搭配的開發骨架。

## 技術架構

- Frontend: Vue 3 + TypeScript + Vite
- Backend: FastAPI + SQLAlchemy
- Database: PostgreSQL 16 + pgvector
- Migration: Alembic
- Embedding: `patrickjohncyh/fashion-clip`（512 維、cosine distance）
- Virtual try-on: 獨立 CatVTON GPU API + 私有 MinIO


## 系統流程圖

系統分成「衣服資料準備」、「使用者推薦流程」和「穿搭規則更新」三個部分。

```mermaid
flowchart TD
    A[styles.csv 與衣服圖片] --> B[匯入 clothes]
    B --> C[判斷 garment_zone]
    C --> D[FashionCLIP 建立圖片 embedding]

    U[使用者輸入穿搭需求] --> Q[Query Planner / Agent]
    P[user_preferences] --> Q
    Q --> R[產生多個英文搜尋 query]
    R --> S{使用者確認}
    S -->|刪除、保留或補充需求| Q
    S -->|確認| E[FashionCLIP 文字 embedding 搜尋]
    D --> E
    E --> T[取得上身、下身與套裝候選]
    T --> O[Outfit Ranker 組合與評分]
    F[fashion_rules] --> O
    P --> O
    O --> V[顯示最高分搭配]
    V --> L[使用者選擇喜歡的搭配]
    L --> X[產生偏好更新提案]
    X --> Y{使用者確認}
    Y -->|同意| P

    N[新聞與穿搭文章] --> G[Fashion Rule Agent]
    G --> H[產生規則草稿與來源]
    H --> I{人工審核}
    I -->|通過| F
```

## Project structure

```text
backend/
├── app/
│   ├── api/                 # FastAPI routes
│   ├── knowledge/           # 文章收集、JSON、DB import、knowledge retrieval
│   ├── preferences/         # preference context 等 domain logic
│   ├── services/
│   │   ├── query_planner.py
│   │   ├── catalog_search.py
│   │   ├── outfit_ranker.py
│   │   ├── aesthetic_reviewer.py
│   │   └── integration_tools/  # LLM、FashionCLIP、text embeddings adapters
│   ├── models/              # SQLAlchemy models
│   └── schemas/             # API / internal Pydantic schemas
├── scripts/                 # catalog、article、knowledge 的離線工作
└── alembic/                 # DB migrations

frontend/
└── src/
    ├── views/               # AgentSearch、Preferences 等畫面
    └── api.ts               # Backend API calls

docs/
├── RECOMMENDATION_PIPELINE.md
├── FASHION_KNOWLEDGE_DB.md
└── KAGGLE_CURATION.md
```

## 當前實作流程與資料來源

### 商品 catalog

商品資料由 Kaggle `styles.csv` 與 `{id}.jpg` 圖片組成。

1. `scripts.import_catalog` 將商品 metadata、價格、圖片位置與 `garment_zone` 寫入 `clothes`。
2. `scripts.build_embeddings` 使用 FashionCLIP 為每件商品圖片建立 512 維 embedding。
3. 線上搜尋會以 FashionCLIP 的文字 embedding，在 `clothes.embedding` 做 cosine vector search。

一般匯入操作見 README 下方「匯入衣服資料」；大型資料集的 Kaggle curation、下載與精選流程見 [`docs/KAGGLE_CURATION.md`](docs/KAGGLE_CURATION.md)。

### Fashion knowledge

文章知識由公開穿搭文章整理而來：

1. `scripts.collect_articles` 收集文章、圖片，並用 LLM 萃取 `outfit observations`。
2. 萃取結果先存為 `data/articles/records/*.json`。
3. `scripts.import_fashion_knowledge` 將 records 寫入 `fashion_articles`、`fashion_observations`，並建立 text embeddings。
4. Query Planner 與 recommendation 會依 user input 從 observations 做 semantic retrieval。

完整收集、匯入、資料表與 retrieval 說明見 [`docs/FASHION_KNOWLEDGE_DB.md`](docs/FASHION_KNOWLEDGE_DB.md)。


### 使用者推薦流程
1. 使用者輸入自然語言需求，前端呼叫 `POST /api/query-plans`。

2. 後端取得：
   - user input
   - hard / soft preferences
   - semantic fashion knowledge observations
   - inferred 或明確指定的 audience

3. `QueryPlanner` 將上述資料提供給 LLM，產生固定六個 FashionCLIP query drafts：
   - 2 個 `upper_body`
   - 2 個 `lower_body`
   - 2 個 `one_piece`

4. Query Planner 驗證 query zone distribution，並將 query 正規化為適合 FashionCLIP 的簡短英文視覺描述；若輸出不合法，會嘗試修復。

5. 使用者可直接修改 query、取消選取或刪除 query。直接編輯不會重新呼叫 LLM；只有使用者輸入補充需求時，前端才呼叫 `POST /api/query-plans/refine`，以既有 queries 與補充需求重新規劃。

6. 使用者按下查詢後，前端呼叫 `POST /api/recommendations`，傳送已選取的 queries、原始 user input、user key 與 audience。

7. Recommendation endpoint 會再次依 user input 取得 semantic fashion knowledge observations，作為結果 metadata 與後續 Aesthetic Reviewer context。

8. `catalog_search` 將已選取的 queries 轉成 FashionCLIP text embeddings，並在 `clothes.embedding` 做 cosine vector search。搜尋時會套用：
   - 相同的 `garment_zone`
   - audience 對應的商品 gender
   - 價格 hard filters
   - 排除顏色、article type、master category 等 avoid filters

   若 avoid filters 使某個 zone 沒有候選商品，該 zone 會暫時放寬 avoid filters；價格、audience 與 garment zone 仍會保留。

9. `rank_outfits` 將上衣與下身候選組合，或將 `one_piece` 作為完整 outfit。它依 FashionCLIP similarity、商品相容性、user input context 與 soft preferences 評分。

10. `select_diverse` 從高分結果中建立 shortlist，避免商品、圖片、色彩或搭配組合過度重複。

11. 若啟用 Aesthetic Reviewer，vision LLM 會審查 shortlist 的實際商品圖片；`apply_aesthetic_reviews` 合併原始 ranking 與 aesthetic score，輸出最終推薦。若 reviewer 未啟用或失敗，系統直接使用 ranking 結果。

12. 使用者可以對喜歡的商品按愛心。前端呼叫 preference proposal API 產生 soft preference proposals；只有使用者確認後，才寫入 user preferences。

## 預期流程
### 使用者推薦流程

1. 使用者輸入場合、風格、顏色、預算或不想要的項目。
2. Query Planner 參考輸入內容與 `user_preferences`，拆成多個英文 query，並標記搜尋的 `garment_zone`。
3. 使用者可以保留、刪除 query，或補充「還要什麼／不要什麼」後重新拆解。
4. 使用者確認後，FashionCLIP 將 query 轉成文字 embedding。
5. 系統在相同 `garment_zone` 中，以 cosine distance 搜尋最接近的衣服圖片：
   - `upper_body` query 只搜尋上半身衣服。
   - `lower_body` query 只搜尋下半身衣服。
   - `one_piece` query 只搜尋洋裝或連身服。
6. Outfit Ranker 將上身與下身候選配對，`one_piece` 則直接作為完整搭配候選。
7. 預計使用 embedding 相似度、`fashion_rules`、使用者偏好、價格與場合適合度計算總分。
8. 前端顯示最高分的幾組上下身搭配或單件套裝。
9. 使用者選擇喜歡的衣服後，系統先提出偏好更新內容；只有使用者確認後才寫入 `user_preferences`。

### 穿搭規則更新流程

1. Fashion Rule Agent 定期讀取新聞或穿搭文章。
2. Agent 將文章整理成固定欄位的規則草稿，並保留 `source_url`、發布時間和適用條件。
3. 規則先經人工審核，通過後才設為 `is_active=true`。
4. Outfit Ranker 只使用已啟用的規則參與搭配評分。

第一版不把雜誌內容直接寫成永久真理，也不自動啟用 `fashion_rules`。文章先存成 `data/articles/records/*.json` 的 `outfit observations`，每一筆保留來源、證據、適用情境、單品、顏色、材質、輪廓、搭配動作、時效類型與信心分數。待格式穩定且經人工抽查後，再決定哪些內容值得晉升成資料庫規則。

### 目前實作狀態

- 已完成：CSV 與圖片匯入、garment zone 分類、圖片 embedding、文字 embedding 搜尋、query 確認介面、基本上下身配對、偏好更新提案與確認。
- 已完成：LLM Query Planner 會產生六個可編輯的 FashionCLIP queries；確認後由 Catalog Search、Outfit Ranker、多樣性篩選與可選的 Aesthetic Reviewer 產生實際商品搭配。
- 已完成：指定 URL 文章收集、圖片與文字的 LLM 結構化整理、semantic fashion knowledge retrieval，用於 Query Planner 與 recommendation context。

## 啟動服務

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- API health: http://localhost:8000/health
- PostgreSQL: `localhost:5432`

一般網站 stack 不會啟動 CatVTON 或 MinIO。未設定遠端 GPU API 時，虛擬試穿分頁會顯示服務尚未連線，其餘功能可正常使用。

## 虛擬試穿部署

CatVTON 與 MinIO 有獨立的 Compose stack，位於 `catvton/`。它不使用或連接 Matching Outfit 的 PostgreSQL；MinIO 只存在於 CatVTON 私有 Docker network，保存排隊中的輸入、job manifest 與生成結果。

在 NVIDIA Linux 主機上設定：

```bash
cd catvton
cp .env.example .env
# 編輯 .env，替換 CATVTON_API_KEY、MINIO_ROOT_USER、MINIO_ROOT_PASSWORD
docker compose up --build -d
```

CatVTON API 預設監聽 `9002`。MinIO API 不發布到主機；管理 console 只綁定 `127.0.0.1:9001`，需要遠端管理時可透過 SSH tunnel 使用。

第一次啟動會從 Hugging Face 下載 CatVTON、DensePose、SCHP 與 base model，需等待模型下載及載入完成。健康檢查需要 API key：

```bash
curl -H "X-API-Key: $CATVTON_API_KEY" http://127.0.0.1:9002/health
```

網站主機透過私有網路或 VPN 設定同一組 secret：

```bash
cp .env.example .env
# CATVTON_API_URL=http://<GPU_PRIVATE_IP>:9002
# CATVTON_API_KEY=<與 GPU 主機相同的 secret>
docker compose up --build -d
```

人物照與衣服照由 CatVTON 在工作結束後立即從 MinIO 刪除；結果與 manifest 保存 24 小時。Matching Outfit backend 只保存本地 job metadata 和遠端 job UUID，前端不會取得 MinIO 帳密或 CatVTON API key。

Backend 啟動前會自動執行 `alembic upgrade head`。這次 initial migration 已重建；若你曾用舊版 schema 建立 Docker volume，請先執行：

```bash
docker compose down -v
docker compose up --build
```

## 少量文章 → 穿搭知識

1. 複製環境設定並填入 API key：

```bash
cp .env.example .env
```

2. 複製 `data/article_urls.example.txt`，先挑 8–12 篇公開且能直接閱讀的文章，一行一個 URL。第一版只接受設定中的 ELLE Taiwan、GQ Taiwan、Marie Claire Korea 與 GQ Korea 網域，不會從分類頁自動無限追蹤連結。

3. 先只測試網頁解析，不花 LLM 用量：

```bash
docker compose run --rm backend python -m scripts.collect_articles \
  --url-file /data/article_urls.example.txt \
  --collect-only
```

4. 確認 `data/articles/raw/` 內容合理後，再下載每篇最多 4 張圖片並抽取穿搭觀察：

```bash
docker compose run --rm backend python -m scripts.collect_articles \
  --url-file /data/article_urls.example.txt \
  --download-images \
  --max-images 4
```

收集器預設遵守 `robots.txt`、限制允許網域，也不處理登入或付費牆。網站條款與頁面結構仍可能改變；失敗的文章會個別列出，不會偷偷換來源。原始文章、衍生 JSON 和下載圖片都被 `.gitignore` 排除，不會塞進 Git。

將已抽取的 `data/articles/records/*.json` 寫入 PostgreSQL 並建立 knowledge embeddings：

```bash
docker compose exec backend python -m scripts.import_fashion_knowledge
```

可用 `GET /api/fashion-knowledge/status` 查看已匯入的文章與 observations 數量。

## 放置 Kaggle 資料

如果不想人工挑選，也不想把 15 GB 高畫質資料下載到本機，可以先在 Kaggle Notebook 執行 `scripts.curate_catalog`。它會以 metadata、圖片品質、FashionCLIP、去重與多樣性 quota 全自動選出約 500 件，再只複製入選 ID 的高畫質圖。完整操作見 [`docs/KAGGLE_CURATION.md`](docs/KAGGLE_CURATION.md)。

下載 [Fashion Product Images Dataset](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset) 並整理成以下結構：

```text
data/
├── styles.csv
└── images/
    ├── 1163.jpg
    ├── 1164.jpg
    └── ...
```

重點是 CSV 的 `id` 必須對應到 `images/{id}.jpg`。Docker 會把整個 `data/` 唯讀掛載到 backend 的 `/data/`。

## 匯入衣服資料

先測試 100 筆，未提供價格的 Kaggle 資料會暫時填入整數 `1000`：

```bash
docker compose exec backend python -m scripts.import_catalog \
  --csv /data/styles.csv \
  --image-dir /data/images \
  --default-price 1000 \
  --limit 100
```

確認後移除 `--limit 100` 即可匯入全部。重複執行會依 `source_item_id` 更新，不會建立重複衣服。

匯入 catalog 後，建立尚未有向量的商品圖片 embeddings：
```bash
docker compose exec backend python -m scripts.build_embeddings \
  --batch-size 8
```


匯入工具會填入：

- Kaggle 欄位：`gender`、`master_category`、`sub_category`、`article_type`、`base_colour`、`season`、`year`、`usage`、`product_display_name`
- `source_item_id`: Kaggle `id`
- `price`: 目前由 `--default-price` 指定，之後可換成真實價格
- `image_path`: backend 讀圖使用，例如 `/data/images/1163.jpg`
- `image_url`: 前端顯示使用，例如 `/media/1163.jpg`
- `garment_zone`: 依 article type/subcategory 自動分為 `upper_body`、`lower_body`、`one_piece`、`accessory`、`other`

分類規則位於 `backend/app/services/garment_classifier.py`。正式匯入前建議先抽樣確認，因為 Kaggle 類別中還有印度服飾等需要依產品定義調整的項目。

## 資料表

- `clothes`: 商品 metadata、圖片位置、衣服區域、價格與 512 維 embedding。
- `user_hard_rules`：價格區間與避免條件等 hard filters。
- `user_style_preferences`：使用者確認後保存的 soft preferences。
- `fashion_articles`：文章來源與萃取 metadata。
- `fashion_observations`：可重複使用的穿搭 observation 與 text embedding。

新聞蒐集 agent 後續應只建立或更新規則草稿，保留 `source_url`、`published_at` 與 `reviewed_at`，並在人工確認後才設為 `is_active=true`。
