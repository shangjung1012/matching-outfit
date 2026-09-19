<script setup lang="ts">
import { computed } from 'vue'
import { ArrowLeft, BookOpenText, CheckCircle2, ChevronDown, History, Search, Trash2 } from 'lucide-vue-next'
import type { DebugHistoryItem } from '../composables/useDebugHistory'
import type {
  FashionObservationTrace,
  GarmentZone,
  OutfitRecommendation,
  PipelineDebugSession,
  QueryDraft,
  QuerySearchResult,
  GeneratedQueryTrace,
} from '../types'

const props = defineProps<{
  trace: PipelineDebugSession | null
  history: DebugHistoryItem[]
  selectedId: string | null
}>()
const emit = defineEmits<{
  back: []
  selectHistory: [id: string]
  showCurrent: []
  deleteHistory: [id: string]
}>()

const requirementLabels: Record<string, string> = {
  location: '地點', target_date: '日期', outfit_budget_max: '整套預算',
  occasions: '場合', seasons: '季節', times_of_day: '時段', climates: '氣候',
  formalities: '正式程度', activities: '活動', styles: '風格',
  special_requirements: '特別需求', additional_notes: '補充說明',
}

const requirementRows = computed(() => {
  const requirements = props.trace?.requirements
  if (!requirements) return []
  return Object.entries(requirementLabels).flatMap(([key, label]) => {
    const value = requirements[key as keyof typeof requirements]
    if (Array.isArray(value) && value.length) return [{ label, value: value.join('、') }]
    if (key === 'outfit_budget_max' && typeof value === 'number') return [{ label, value: `$${value.toLocaleString('zh-TW')}` }]
    if (typeof value === 'string' && value.trim()) return [{ label, value }]
    return []
  })
})

const searchResults = computed(() => props.trace?.recommendation_debug?.search_results ?? [])
const searchedItemCount = computed(() => searchResults.value.reduce(
  (total: number, group: QuerySearchResult) => total + group.clothes.length,
  0,
))
const knowledge = computed(() => {
  const recommendationKnowledge = props.trace?.recommendation_debug?.knowledge_observations ?? []
  if (recommendationKnowledge.length) return recommendationKnowledge
  return props.trace?.plan_debug?.knowledge_observations ?? []
})
const knowledgeUsage = computed(() => {
  const usage = new Map<string, QueryDraft[]>()
  for (const query of props.trace?.queries ?? []) {
    for (const observationId of query.knowledge_observation_ids) {
      const related = usage.get(observationId) ?? []
      related.push(query)
      usage.set(observationId, related)
    }
  }
  return usage
})

const timingLabels: Record<string, string> = {
  context_and_knowledge: '需求與文章知識整理',
  fashion_intent: '風格需求理解',
  query_planner: '搭配搜尋方向規劃',
  catalog_search: '商品搜尋',
  outfit_ranker: '搭配組合與初步評分',
  compatibility_rerank: '搭配協調度重排',
  aesthetic_review: '圖片美感評估',
  shoe_retrieval: '鞋款搜尋',
}
const timingRows = computed(() => {
  const planning = props.trace?.plan_debug?.stage_timings_ms ?? {}
  const recommendation = props.trace?.recommendation_debug?.stage_timings_ms ?? {}
  const rows = [
    ...Object.entries(planning).filter(([key]) => key !== 'total'),
    ...Object.entries(recommendation).filter(([key]) => key !== 'total'),
  ].map(([key, value]) => ({ label: timingLabels[key] ?? key, value }))
  if (planning.total !== undefined) rows.push({ label: '規劃階段合計', value: planning.total })
  if (recommendation.total !== undefined) rows.push({ label: '推薦階段合計', value: recommendation.total })
  return rows
})

function zoneLabel(zone: GarmentZone) {
  return { upper_body: '上身', lower_body: '下身', one_piece: '連身單品', accessory: '配件', other: '其他' }[zone]
}
function queryLabel(query: QueryDraft): string {
  return `${zoneLabel(query.garment_zone)}｜${query.rationale}`
}
function matchedQueriesForOutfit(outfit: OutfitRecommendation): QueryDraft[] {
  const zones = new Set(outfit.items.map((item) => item.garment_zone))
  return (props.trace?.queries ?? []).filter((query: QueryDraft) => (
    query.selected
    && query.direction_id === outfit.direction_id
    && zones.has(query.garment_zone)
  ))
}
function outfitPreferenceReferences(outfit: OutfitRecommendation): string[] {
  return Array.from(new Set(
    matchedQueriesForOutfit(outfit).flatMap((query) => query.preference_references || []),
  ))
}
function outfitObservationDetails(outfit: OutfitRecommendation): Array<{
  id: string
  title: string
  url: string
  summary: string
  evidence: string
}> {
  const observationsById = new Map((knowledge.value as FashionObservationTrace[]).map((item) => [item.observation_id, item]))
  const rows = matchedQueriesForOutfit(outfit).flatMap((query) => query.knowledge_observation_ids
    .map((observationId) => observationsById.get(observationId))
    .filter((item): item is FashionObservationTrace => Boolean(item))
    .map((item) => ({
      id: `${query.id}:${item.observation_id}`,
      title: item.source_title || item.source_name || item.source_url,
      url: item.source_url,
      summary: item.summary,
      evidence: item.evidence,
    })))
  return Array.from(new Map(rows.map((row) => [`${row.url}::${row.evidence || row.summary}`, row])).values())
}
function knowledgeSummaries(query: QueryDraft): string {
  return query.knowledge_observation_ids
    .map((id) => knowledge.value.find((item: FashionObservationTrace) => item.observation_id === id)?.summary)
    .filter((summary): summary is string => Boolean(summary))
    .join('；')
}
function outfitName(outfit: OutfitRecommendation): string {
  return outfit.items.map(item => item.product_display_name).join(' + ')
}
function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`
}
function originalQuery(query: QueryDraft): string {
  return props.trace?.plan_debug?.generated_queries_before_normalization.find((item: GeneratedQueryTrace) => (
    item.direction_id === query.direction_id && item.garment_zone === query.garment_zone
  ))?.text ?? query.text
}
function duration(milliseconds: number): string {
  return milliseconds >= 1000 ? `${(milliseconds / 1000).toFixed(2)} 秒` : `${Math.round(milliseconds)} ms`
}
function deleteHistory(id: string) {
  if (window.confirm('確定刪除這份搭配分析？')) emit('deleteHistory', id)
}
</script>

<template>
  <section class="page-view debug-view analysis-view">
    <header class="view-heading debug-heading analysis-heading">
      <div>
        <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="16" />返回推薦搭配</button>
        <span class="section-kicker">Outfit analysis</span>
        <h2>詳細搭配分析</h2>
        <p>從你的需求到最後推薦，查看這次搭配是如何選出的。</p>
      </div>
    </header>

    <details v-if="history.length" class="analysis-history">
      <summary><History :size="16" />過往搭配分析（{{ history.length }}）<ChevronDown :size="15" /></summary>
      <div class="debug-history-list">
        <article v-for="item in history" :key="item.id" class="debug-history-row">
          <button :class="{ active: selectedId === item.id }" @click="emit('selectHistory', item.id)">
            <strong>{{ item.title }}</strong>
            <small>{{ new Date(item.savedAt).toLocaleString('zh-TW') }}{{ selectedId === item.id ? ' · 正在查看' : '' }}</small>
          </button>
          <button class="icon-button danger" title="刪除分析" @click="deleteHistory(item.id)"><Trash2 :size="15" /></button>
        </article>
        <button v-if="selectedId" class="secondary-button" @click="emit('showCurrent')">回到目前結果</button>
      </div>
    </details>

    <div v-if="!trace" class="empty-view debug-empty">
      <Search :size="34" /><h3>還沒有可分析的搭配</h3>
      <p>完成一次找搭配後，就能在這裡看到完整的選擇過程。</p>
      <button class="primary-button" type="button" @click="emit('back')">開始找搭配</button>
    </div>

    <template v-else>
      <section class="analysis-overview" aria-label="分析摘要">
        <article><span>搭配方向</span><strong>{{ trace.queries.length }}</strong><small>組搜尋方向</small></article>
        <article><span>搜尋結果</span><strong>{{ searchedItemCount }}</strong><small>件候選商品</small></article>
        <article><span>搭配候選</span><strong>{{ trace.recommendation_debug?.ranked_candidate_count ?? 0 }}</strong><small>套完成搭配</small></article>
        <article><span>最後推薦</span><strong>{{ trace.recommendations.length }}</strong><small>套精選結果</small></article>
      </section>

      <section class="debug-section analysis-section">
        <header><span>1</span><div><h3>理解你的需求</h3><p>{{ trace.original_input }}</p></div></header>
        <dl v-if="requirementRows.length" class="analysis-requirements">
          <div v-for="row in requirementRows" :key="row.label"><dt>{{ row.label }}</dt><dd>{{ row.value }}</dd></div>
        </dl>
        <div v-else class="debug-panel debug-muted">這次沒有額外的需求條件。</div>
      </section>

      <section class="debug-section analysis-section">
        <header><span>2</span><div><h3>參考穿搭文章</h3><p>先列出這次採用的文章依據，以及哪一句話影響了哪一個搭配方向。</p></div></header>
        <div v-if="knowledge.length" class="analysis-knowledge-list">
          <article v-for="item in knowledge" :key="item.observation_id">
            <BookOpenText :size="17" />
            <div>
              <strong>{{ item.summary }}</strong>
              <p class="analysis-knowledge-evidence">引用句子：{{ item.evidence }}</p>
              <p v-if="knowledgeUsage.get(item.observation_id)?.length" class="analysis-knowledge-usage">
                對應搭配方向：{{ knowledgeUsage.get(item.observation_id)?.map(queryLabel).join('；') }}
              </p>
              <p v-else class="analysis-knowledge-usage">對應搭配方向：此篇文章作為整體風格背景參考。</p>
              <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noreferrer">{{ item.source_title || item.source_name }}</a>
            </div>
          </article>
        </div>
        <div v-else class="debug-panel debug-muted">{{ trace.knowledge_note || '這次沒有使用文章參考。' }}</div>
      </section>

      <section class="debug-section analysis-section">
        <header><span>3</span><div><h3>形成搭配方向</h3><p>將你的場合與風格需求轉換成可搜尋的服裝方向。</p></div></header>
        <div v-if="trace.queries.length" class="analysis-direction-grid">
          <article v-for="query in trace.queries" :key="`${query.direction_id}-${query.garment_zone}`">
            <span>{{ zoneLabel(query.garment_zone) }}</span>
            <div>
              <strong>{{ query.rationale }}</strong>
              <dl class="analysis-query-values">
                <div v-if="query.knowledge_observation_ids.length">
                  <dt>參考文章</dt>
                  <dd>{{ knowledgeSummaries(query) }}</dd>
                </div>
                <div><dt>原始 Query</dt><dd>{{ originalQuery(query) }}</dd></div>
              </dl>
            </div>
          </article>
        </div>
        <div v-else class="debug-panel debug-muted">尚未產生搭配方向。</div>
      </section>

      <section class="debug-section analysis-section">
        <header><span>4</span><div><h3>搜尋合適商品</h3><p>依照每個搭配方向找出外觀與條件相符的商品。</p></div></header>
        <div v-if="searchResults.length" class="debug-details-stack analysis-search-groups">
          <details v-for="group in searchResults" :key="`${group.query.direction_id}-${group.query.garment_zone}`">
            <summary><span>{{ zoneLabel(group.query.garment_zone) }}</span><strong>{{ group.query.rationale }}</strong><small>{{ group.clothes.length }} 件候選</small></summary>
            <div class="debug-product-strip">
              <article v-for="(item, index) in group.clothes.slice(0, 6)" :key="item.id">
                <img :src="item.image_url" :alt="item.product_display_name" />
                <div><strong>#{{ index + 1 }} · 符合度 {{ percent(item.similarity) }}</strong><p>{{ item.product_display_name }}</p><small>{{ item.base_colour }} · {{ item.article_type }}</small></div>
              </article>
            </div>
          </details>
        </div>
        <div v-else class="debug-panel debug-muted">這次沒有保留商品搜尋紀錄。</div>
      </section>

      <section class="debug-section analysis-section">
        <header><span>5</span><div><h3>完成推薦結果</h3><p>綜合場合、配色、輪廓與整體協調度，選出最後搭配。</p></div></header>
        <div v-if="trace.recommendations.length" class="debug-reviewed-grid analysis-result-grid">
          <article v-for="(outfit, index) in trace.recommendations" :key="outfit.id" class="debug-reviewed-card">
            <div class="debug-outfit-images reviewed" :class="{ single: outfit.items.length === 1 }">
              <img v-for="item in outfit.items" :key="item.id" :src="item.image_url" :alt="item.product_display_name" />
            </div>
            <div class="debug-reviewed-copy">
              <div class="debug-outfit-rank"><b>推薦 #{{ index + 1 }}</b><strong>{{ percent(outfit.score) }}</strong></div>
              <h4>{{ outfitName(outfit) }}</h4>
              <div v-if="outfit.aesthetic_review" class="debug-review-scores">
                <span>場合 <b>{{ outfit.aesthetic_review.occasion_fit }}</b></span><span>配色 <b>{{ outfit.aesthetic_review.color_harmony }}</b></span>
                <span>輪廓 <b>{{ outfit.aesthetic_review.silhouette_balance }}</b></span><span>材質 <b>{{ outfit.aesthetic_review.material_coherence }}</b></span>
                <span>整體 <b>{{ outfit.aesthetic_review.overall_aesthetic }}</b></span>
              </div>
              <p>{{ outfit.aesthetic_review?.reason || outfit.reasons.join('；') }}</p>
              <div v-if="outfitPreferenceReferences(outfit).length" class="analysis-result-meta">
                <strong>參考你的偏好</strong>
                <ul>
                  <li v-for="preference in outfitPreferenceReferences(outfit)" :key="preference">{{ preference }}</li>
                </ul>
              </div>
              <div v-if="outfitObservationDetails(outfit).length" class="analysis-result-meta">
                <strong>參考文章</strong>
                <ul>
                  <li v-for="reference in outfitObservationDetails(outfit)" :key="reference.id">
                    <a :href="reference.url" target="_blank" rel="noreferrer">{{ reference.title }}</a>
                    ：{{ reference.evidence || reference.summary }}
                  </li>
                </ul>
              </div>
            </div>
          </article>
        </div>
        <div v-else class="debug-panel debug-muted">尚未取得最終推薦。</div>
      </section>

      <section class="debug-section analysis-section">
        <header><span>6</span><div><h3>各階段處理時間</h3><p>顯示這次搭配分析在每個主要階段花費的時間。</p></div></header>
        <div v-if="timingRows.length" class="analysis-timing-table">
          <div class="analysis-timing-head"><span>處理階段</span><span>耗時</span></div>
          <div v-for="row in timingRows" :key="row.label"><span>{{ row.label }}</span><strong>{{ duration(row.value) }}</strong></div>
        </div>
        <div v-else class="debug-panel debug-muted">這次沒有保留處理時間。</div>
      </section>

      <div class="analysis-end-note"><CheckCircle2 :size="17" />分析完成，共選出 {{ trace.recommendations.length }} 套推薦搭配。</div>
    </template>
  </section>
</template>
