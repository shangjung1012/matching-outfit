<script setup lang="ts">
import { computed } from 'vue'
import type { DebugHistoryItem } from '../composables/useDebugHistory'
import {
  AlertTriangle, BrainCircuit, CheckCircle2, Database, Download, SearchCode,
} from 'lucide-vue-next'
import type {
  GarmentZone,
  OutfitRecommendation,
  PipelineDebugSession,
  QueryDraft,
} from '../types'

const props = defineProps<{
  trace: PipelineDebugSession | null
  history: DebugHistoryItem[]
  selectedId: string | null
  storageError: string
}>()
const emit = defineEmits<{
  selectHistory: [id: string]
  showCurrent: []
  deleteHistory: [id: string]
}>()
function deleteHistory(id: string) {
  if (window.confirm('確定刪除這份除錯快照？此操作不會刪除商品、文章或其他分析。')) emit('deleteHistory', id)
}

const reviewedCandidates = computed(() => [
  ...(props.trace?.recommendations ?? []),
  ...(props.trace?.discarded_recommendations ?? []),
])

const requirementRows = computed(() => {
  const requirements = props.trace?.requirements
  if (!requirements) return []
  return Object.entries(requirements).filter(([key]) => key !== 'tag_translations')
})

function zoneLabel(zone: GarmentZone) {
  return {
    upper_body: '上身',
    lower_body: '下身',
    one_piece: '單件連身',
    accessory: '配件',
    other: '其他',
  }[zone]
}

function displayValue(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.join('、') : '—'
  if (typeof value === 'object' && value !== null) return JSON.stringify(value, null, 2)
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function afterQuery(directionId: string, zone: GarmentZone): QueryDraft | undefined {
  return props.trace?.plan_debug?.generated_queries_after_normalization.find(
    (query) => query.direction_id === directionId && query.garment_zone === zone,
  )
}

function currentQuery(directionId: string, zone: GarmentZone): QueryDraft | undefined {
  return props.trace?.queries.find(
    (query) => query.direction_id === directionId && query.garment_zone === zone,
  )
}

function outfitName(outfit: OutfitRecommendation): string {
  return outfit.items.map((item) => item.product_display_name).join(' + ')
}

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`
}

function downloadTrace() {
  if (!props.trace) return
  const blob = new Blob([JSON.stringify(props.trace, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `outfit-debug-${props.trace.updated_at.replace(/[:.]/g, '-')}.json`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <section class="page-view debug-view">
    <header class="view-heading debug-heading">
      <div>
        <span class="section-kicker">Pipeline inspector</span>
        <h2>推薦流程除錯</h2>
        <p>每次階段更新自動保存為快照，可選取歷史紀錄查看完整分析。</p>
      </div>
      <button v-if="trace" class="secondary-button" @click="downloadTrace">
        <Download :size="16" />下載完整 JSON
      </button>
    </header>

    <section class="debug-panel debug-history">
      <h3>分析歷史（{{ history.length }} 筆）</h3>
      <p>保存在這個瀏覽器；重新整理後仍可查看。不會自動同步到隊友或其他裝置。圖片保留連結，原圖刪除後可能無法顯示。</p>
      <p v-if="storageError" class="chat-error" role="alert">{{ storageError }}</p>
      <button class="secondary-button" @click="emit('showCurrent')">查看目前分析</button>
      <div class="debug-history-list">
        <article v-for="item in history" :key="item.id" class="debug-history-row">
          <button :class="{ active: selectedId === item.id }" @click="emit('selectHistory', item.id)">
            <strong>{{ item.title }}</strong>
            <small>{{ new Date(item.savedAt).toLocaleString('zh-TW') }} · {{ item.stage }}{{ selectedId === item.id ? ' · 正在查看' : '' }}</small>
          </button>
          <button class="secondary-button" @click="deleteHistory(item.id)">刪除快照</button>
        </article>
      </div>
      <p v-if="!history.length">尚未保存分析；後續有使用者需求的階段更新會自動保存。</p>
    </section>

    <div v-if="!trace" class="empty-view debug-empty">
      <SearchCode :size="34" />
      <h3>尚無流程紀錄</h3>
      <p>先到 Agent 搜尋輸入需求；每完成一個階段，這裡就會更新。</p>
    </div>

    <template v-else>
      <div class="debug-summary-grid">
        <article>
          <span>最後更新</span>
          <strong>{{ new Date(trace.updated_at).toLocaleString('zh-TW') }}</strong>
        </article>
        <article>
          <span>Intent</span>
          <strong>{{ trace.fashion_intent ? '已產生' : '尚未產生' }}</strong>
        </article>
        <article>
          <span>搜尋 query</span>
          <strong>{{ trace.queries.length }} 條</strong>
        </article>
        <article>
          <span>Ranker 候選</span>
          <strong>{{ trace.recommendation_debug?.ranked_candidate_count ?? 0 }} 套</strong>
        </article>
      </div>

      <section class="debug-section">
        <header><span>1</span><div><h3>原始對話與 RequirementSummary</h3><p>先確認語意是否在需求整理時就已經偏掉。</p></div></header>
        <div class="debug-two-columns">
          <div class="debug-panel">
            <h4>對話</h4>
            <div class="debug-conversation">
              <p v-for="(message, index) in trace.messages" :key="index" :class="message.role">
                <strong>{{ message.role === 'user' ? '使用者' : 'Agent' }}</strong>{{ message.text }}
              </p>
            </div>
          </div>
          <div class="debug-panel">
            <h4>結構化需求</h4>
            <dl class="debug-definition-list">
              <div v-for="([key, value]) in requirementRows" :key="key">
                <dt>{{ key }}</dt><dd>{{ displayValue(value) }}</dd>
              </div>
            </dl>
          </div>
        </div>
      </section>

      <section class="debug-section">
        <header><span>2</span><div><h3>Fashion Intent Interpreter</h3><p>檢查抽象需求被解讀成什麼形象、視覺線索與搭配策略。</p></div></header>
        <details class="debug-panel" open>
          <summary>產生 query 前的文章知識與缺口</summary>
          <p>{{ trace.plan_debug?.knowledge_note }}</p>
          <p v-if="!trace.plan_debug?.knowledge_used_ids?.length">本次未採用合適的文章句子；以下缺口是規劃診斷，非全庫不存在的證明。</p>
          <ul><li v-for="gap in trace.plan_debug?.knowledge_gaps" :key="gap">待補充：{{ gap }}</li></ul>
          <article v-for="item in trace.plan_debug?.knowledge_observations" :key="item.observation_id">
            <strong>{{ trace.plan_debug?.knowledge_used_ids?.includes(item.observation_id) ? '已採用' : '已檢索但未採用' }}</strong>
            <p>{{ item.summary }}</p>
            <a :href="item.source_url" target="_blank" rel="noopener noreferrer">{{ item.source_title || item.source_url }}</a>
          </article>
        </details>
        <div v-if="trace.fashion_intent" class="debug-panel">
          <div class="debug-intent-title">
            <div><small>USER GOAL</small><h4>{{ trace.fashion_intent.user_goal }}</h4></div>
            <strong>信心 {{ percent(trace.fashion_intent.confidence) }}</strong>
          </div>
          <div v-if="trace.fashion_intent.activity_context" class="debug-panel">
            <h4>活動雙軸判斷</h4>
            <p>有活動：{{ trace.fashion_intent.activity_context.activity_present ? '是' : '否' }} ·
              造型優先度：{{ trace.fashion_intent.activity_context.appearance_priority }} ·
              機能優先度：{{ trace.fashion_intent.activity_context.functional_priority }}</p>
            <p>視覺身分：{{ trace.fashion_intent.activity_context.requested_visual_identity || '未提供' }}</p>
            <p>最低機能：{{ trace.fashion_intent.activity_context.minimum_functional_requirements.join('、') || '無' }}</p>
            <p>明確機能：{{ trace.fashion_intent.activity_context.explicit_functional_requests?.join('、') || '無' }}</p>
            <p>避免偏移：{{ trace.fashion_intent.activity_context.avoid_style_drift?.join('、') || '無' }}</p>
          </div>
          <div class="debug-chip-groups">
            <div><b>目標印象</b><span v-for="item in trace.fashion_intent.desired_impression" :key="item">{{ item }}</span></div>
            <div><b>必須線索</b><span v-for="item in trace.fashion_intent.must_have_visual_cues" :key="item">{{ item }}</span></div>
            <div><b>避免誤解</b><span v-for="item in trace.fashion_intent.avoid_concepts" :key="item" class="warning">{{ item }}</span></div>
            <div><b>搭配原則</b><span v-for="item in trace.fashion_intent.styling_principles" :key="item">{{ item }}</span></div>
          </div>
          <div class="debug-context-row">
            <span>情境：{{ trace.fashion_intent.occasion_interpretation.social_context }}</span>
            <span>正式度：{{ percent(trace.fashion_intent.occasion_interpretation.formality_target) }}</span>
            <span>視覺強度：{{ trace.fashion_intent.occasion_interpretation.visual_impact }}</span>
            <span>實用性：{{ trace.fashion_intent.occasion_interpretation.practicality }}</span>
          </div>
          <div class="debug-concept-grid">
            <article v-for="concept in trace.fashion_intent.concepts" :key="concept.direction_id">
              <strong>{{ concept.direction_id }}</strong>
              <div><h4>{{ concept.concept_name }}</h4><p>{{ concept.outfit_formula }}</p></div>
              <dl>
                <div v-if="concept.upper_role"><dt>上身</dt><dd>{{ concept.upper_role }}</dd></div>
                <div v-if="concept.lower_role"><dt>下身</dt><dd>{{ concept.lower_role }}</dd></div>
                <div v-if="concept.one_piece_role"><dt>連身</dt><dd>{{ concept.one_piece_role }}</dd></div>
                <div><dt>可見線索</dt><dd>{{ concept.visible_cues.join('、') }}</dd></div>
                <div><dt>平衡規則</dt><dd>{{ concept.balance_rules.join('、') }}</dd></div>
              </dl>
            </article>
          </div>
          <p v-if="trace.plan_debug?.intent_fallback_used" class="debug-warning">
            <AlertTriangle :size="15" />Interpreter 失敗，本次已回退舊 Planner。
          </p>
        </div>
        <div v-else class="debug-panel debug-muted">尚未產生 Intent，或本次使用了 fallback。</div>
      </section>

      <section class="debug-section">
        <header><span>3</span><div><h3>Query Planner 與 Normalizer</h3><p>逐條比較 LLM 原始 query 與真正送入 FashionCLIP 的內容。</p></div></header>
        <div v-if="trace.plan_debug" class="debug-panel">
          <div class="debug-meta-line">
            <span>模型：{{ trace.plan_debug.model }}</span>
            <span>Prompt：{{ trace.plan_debug.prompt_version }}</span>
            <span>修改 {{ trace.plan_debug.normalizer_changes.length }} 條</span>
          </div>
          <div v-if="trace.plan_debug.query_warnings.length" class="debug-warning-list">
            <strong><AlertTriangle :size="15" />Query warnings</strong>
            <p v-for="warning in trace.plan_debug.query_warnings" :key="warning">{{ warning }}</p>
          </div>
          <div class="debug-table-wrap">
            <table class="debug-table">
              <thead><tr><th>方向</th><th>區域</th><th>Normalizer 前</th><th>Normalizer 後</th><th>目前／實際搜尋</th></tr></thead>
              <tbody>
                <tr v-for="query in trace.plan_debug.generated_queries_before_normalization" :key="`${query.direction_id}-${query.garment_zone}`">
                  <td><b>{{ query.direction_id }}</b></td>
                  <td>{{ zoneLabel(query.garment_zone) }}</td>
                  <td>{{ query.text }}</td>
                  <td :class="{ changed: afterQuery(query.direction_id, query.garment_zone)?.text !== query.text }">
                    {{ afterQuery(query.direction_id, query.garment_zone)?.text ?? '—' }}
                  </td>
                  <td>{{ currentQuery(query.direction_id, query.garment_zone)?.selected ? currentQuery(query.direction_id, query.garment_zone)?.text : '已取消選取' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-else class="debug-panel debug-muted">確認需求並產生 query 後，這裡會顯示 Planner trace。</div>
      </section>

      <section class="debug-section">
        <header><span>4</span><div><h3>FashionCLIP 商品召回</h3><p>每條 query 的 top-10 商品與向量相似度；這裡能判斷是 query 還是資料集出問題。</p></div></header>
        <div v-if="trace.recommendation_debug?.search_results.length" class="debug-details-stack">
          <details v-for="group in trace.recommendation_debug.search_results" :key="group.query.id">
            <summary>
              <span>{{ group.query.direction_id }} · {{ zoneLabel(group.query.garment_zone) }}</span>
              <strong>{{ group.query.text }}</strong>
              <small>{{ group.clothes.length }} 件</small>
            </summary>
            <div class="debug-product-strip">
              <article v-for="item in group.clothes" :key="item.id">
                <img :src="item.image_url" :alt="item.product_display_name" />
                <div><strong>{{ percent(item.similarity) }}</strong><p>{{ item.product_display_name }}</p><small>{{ item.base_colour }} · {{ item.article_type }}</small></div>
              </article>
            </div>
          </details>
        </div>
        <div v-else class="debug-panel debug-muted">執行「開始搭配」後才會取得 FashionCLIP 候選。</div>
      </section>

      <section class="debug-section">
        <header><span>5</span><div><h3>Outfit Ranker 與 shortlist</h3><p>顯示規則初排規模、前 30 名預覽及送進視覺審查的候選（最多 30 套）。</p></div></header>
        <div v-if="trace.recommendation_debug" class="debug-panel">
          <p class="debug-count-line"><Database :size="16" />產生 {{ trace.recommendation_debug.ranked_candidate_count }} 套組合，shortlist {{ trace.recommendation_debug.shortlist_before_review.length }} 套。</p>
          <details>
            <summary>查看初排前 {{ trace.recommendation_debug.ranked_preview.length }} 名</summary>
            <div class="debug-outfit-grid">
              <article v-for="(outfit, index) in trace.recommendation_debug.ranked_preview" :key="outfit.id" class="debug-outfit-card">
                <div class="debug-outfit-images" :class="{ single: outfit.items.length === 1 }">
                  <img v-for="item in outfit.items" :key="item.id" :src="item.image_url" :alt="item.product_display_name" />
                </div>
                <div class="debug-outfit-copy">
                  <div class="debug-outfit-rank"><b>#{{ index + 1 }}</b><strong>{{ percent(outfit.score) }}</strong></div>
                  <p>{{ outfitName(outfit) }}</p>
                  <dl><div><dt>FashionCLIP</dt><dd>{{ percent(outfit.score_breakdown?.fashion_clip) }}</dd></div><div><dt>相容性</dt><dd>{{ percent(outfit.score_breakdown?.compatibility) }}</dd></div><div><dt>場合</dt><dd>{{ percent(outfit.score_breakdown?.context_fit) }}</dd></div></dl>
                </div>
              </article>
            </div>
          </details>
          <details>
            <summary>查看送給視覺 LLM 的 shortlist</summary>
            <div class="debug-outfit-grid shortlist">
              <article v-for="(outfit, index) in trace.recommendation_debug.shortlist_before_review" :key="outfit.id" class="debug-outfit-card">
                <div class="debug-outfit-images" :class="{ single: outfit.items.length === 1 }">
                  <img v-for="item in outfit.items" :key="item.id" :src="item.image_url" :alt="item.product_display_name" />
                </div>
                <div class="debug-outfit-copy">
                  <div class="debug-outfit-rank"><b>送審 #{{ index + 1 }}</b><strong>{{ percent(outfit.score) }}</strong></div>
                  <p>{{ outfitName(outfit) }}</p>
                  <small>{{ outfit.kind === 'separates' ? '上下身搭配' : '單件連身' }} · 視覺審查前分數</small>
                </div>
              </article>
            </div>
          </details>
        </div>
        <div v-else class="debug-panel debug-muted">尚未執行搭配。</div>
      </section>

      <section class="debug-section">
        <header><span>6</span><div><h3>文章知識檢索</h3><p>列出本次送入 Aesthetic Reviewer 的 observations，而不只顯示文章名稱。</p></div></header>
        <div v-if="trace.recommendation_debug?.knowledge_observations.length" class="debug-details-stack">
          <details v-for="item in trace.recommendation_debug.knowledge_observations" :key="item.observation_id">
            <summary><span>{{ item.signal_type }}</span><strong>{{ item.summary }}</strong><small>{{ percent(item.confidence) }}</small></summary>
            <div class="debug-detail-body"><p><b>證據：</b>{{ item.evidence }}</p><p><b>標籤：</b>{{ [...item.styles, ...item.garments, ...item.colors, ...item.materials].join('、') || '—' }}</p><a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noreferrer">{{ item.source_title || item.source_name || item.source_url }}</a></div>
          </details>
        </div>
        <div v-else class="debug-panel debug-muted">{{ trace.knowledge_note || '本次沒有檢索到或使用文章知識。' }}</div>
      </section>

      <section class="debug-section">
        <header><span>7</span><div><h3>Aesthetic Reviewer 與最終重排</h3><p>比較最佳 10 套和其他候選的各項視覺評分及致命問題；漏審候選不列入最終推薦。</p></div></header>
        <div v-if="reviewedCandidates.length" class="debug-panel">
          <p class="debug-count-line">
            <component :is="trace.recommendation_debug?.aesthetic_review_error ? AlertTriangle : CheckCircle2" :size="16" />
            {{ trace.review_note || '審查完成' }}
          </p>
          <p v-if="trace.recommendation_debug?.aesthetic_review_error" class="debug-warning">{{ trace.recommendation_debug.aesthetic_review_error }}</p>
          <section v-if="trace.recommendation_debug?.aesthetic_review_diagnostics?.submitted_ids" class="debug-review-diagnostics">
            <h4>美感審查完整性與補審紀錄</h4>
            <p>
              候選 {{ trace.recommendation_debug.aesthetic_review_diagnostics.candidate_count }} 套 ·
              可送審 {{ trace.recommendation_debug.aesthetic_review_diagnostics.submitted_ids.length }} 套 ·
              有效評分 {{ trace.recommendation_debug.aesthetic_review_diagnostics.reviewed_count }} 套 ·
              圖片失敗 {{ trace.recommendation_debug.aesthetic_review_diagnostics.image_failures.length }} 套 ·
              補審後缺評分 {{ trace.recommendation_debug.aesthetic_review_diagnostics.missing_ids.length }} 套
            </p>
            <details v-for="(attempt, index) in trace.recommendation_debug.aesthetic_review_diagnostics.attempts" :key="index">
              <summary>
                {{ attempt.round === 0 ? '首次審查' : '補審第 ' + attempt.round + ' 輪' }}：
                送出 {{ attempt.requested_ids.length }} ／ 回覆 {{ attempt.returned_ids.length }} ／
                缺漏 {{ attempt.missing_ids.length }} ／ 無效 ID {{ attempt.invalid_ids.length }} ／
                重複 ID {{ attempt.duplicate_ids.length }}
              </summary>
              <pre>{{ JSON.stringify(attempt, null, 2) }}</pre>
            </details>
            <details v-if="trace.recommendation_debug.aesthetic_review_diagnostics.image_failures.length">
              <summary>查看圖片失敗的商品 ID 與原因</summary>
              <pre>{{ JSON.stringify(trace.recommendation_debug.aesthetic_review_diagnostics.image_failures, null, 2) }}</pre>
            </details>
          </section>
          <div class="debug-reviewed-grid">
            <article
              v-for="(outfit, index) in reviewedCandidates"
              :key="outfit.id"
              class="debug-reviewed-card"
              :class="{ discarded: index >= trace.recommendations.length }"
            >
              <div class="debug-outfit-images reviewed" :class="{ single: outfit.items.length === 1 }">
                <img v-for="item in outfit.items" :key="item.id" :src="item.image_url" :alt="item.product_display_name" />
              </div>
              <div class="debug-reviewed-copy">
                <div class="debug-outfit-rank">
                  <b>{{ index < trace.recommendations.length ? `最終推薦 #${index + 1}` : '未入選' }}</b>
                  <strong>{{ percent(outfit.score) }}</strong>
                </div>
                <h4>{{ outfitName(outfit) }}</h4>
                <div class="debug-review-scores">
                  <span>場合 <b>{{ outfit.aesthetic_review?.occasion_fit ?? '—' }}</b></span>
                  <span>配色 <b>{{ outfit.aesthetic_review?.color_harmony ?? '—' }}</b></span>
                  <span>輪廓 <b>{{ outfit.aesthetic_review?.silhouette_balance ?? '—' }}</b></span>
                  <span>材質 <b>{{ outfit.aesthetic_review?.material_coherence ?? '—' }}</b></span>
                  <span>美感 <b>{{ outfit.aesthetic_review?.overall_aesthetic ?? '—' }}</b></span>
                  <span>風格吻合 <b>{{ outfit.aesthetic_review?.style_identity_match ?? '—' }}</b></span>
                  <span>搭配協調 <b>{{ outfit.aesthetic_review?.pairing_coherence ?? '—' }}</b></span>
                  <span>限制遵守 <b>{{ outfit.aesthetic_review?.constraint_compliance ?? '—' }}</b></span>
                </div>
                <p>{{ outfit.aesthetic_review?.reason || outfit.reasons.join('；') }}</p>
                <p v-if="outfit.aesthetic_review?.style_drift_detected">
                  重大風格偏移證據：{{ outfit.aesthetic_review.style_drift_evidence?.join('；') }}
                </p>
                <p v-if="outfit.aesthetic_review?.local_fallback_fields?.length" class="debug-warning">
                  本機 fallback，非模型判斷：{{ outfit.aesthetic_review.local_fallback_fields.join('、') }}
                </p>
                <em v-if="outfit.aesthetic_review?.fatal_issues.length">Fatal：{{ outfit.aesthetic_review.fatal_issues.join('、') }}</em>
              </div>
            </article>
          </div>
        </div>
        <div v-else class="debug-panel debug-muted">尚未取得最終推薦。</div>
      </section>

      <details class="debug-raw-json">
        <summary><BrainCircuit :size="16" />查看完整原始 JSON</summary>
        <pre>{{ JSON.stringify(trace, null, 2) }}</pre>
      </details>
    </template>
  </section>
</template>
