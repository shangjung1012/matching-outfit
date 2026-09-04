<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  BookOpenText, ChevronDown, ExternalLink, LoaderCircle, Plus,
  RefreshCw, Search, Trash2,
} from 'lucide-vue-next'
import {
  autoUpdateFashionArticles, collectFashionArticles, deleteFashionArticle, getFashionArticles,
  getFashionKnowledgeSources,
  setFashionObservationActive,
} from '../api'
import type {
  FashionArticleAdmin, FashionArticleCollectResult, FashionKnowledgeSource,
} from '../types'

const articles = ref<FashionArticleAdmin[]>([])
const total = ref(0)
const search = ref('')
const urlInput = ref('')
const loading = ref(false)
const collecting = ref(false)
const error = ref('')
const notice = ref('')
const expandedIds = ref(new Set<number>())
const collectResults = ref<FashionArticleCollectResult[]>([])
const sources = ref<FashionKnowledgeSource[]>([])
const selectedSourceKeys = ref<string[]>([])
const perSourceLimit = ref(2)
const pageLimit = ref(0)
const discoveryErrors = ref<Record<string, string>>({})

const observationTotal = computed(() =>
  articles.value.reduce((sum, article) => sum + article.observation_count, 0),
)
const activeObservationTotal = computed(() =>
  articles.value.reduce((sum, article) => sum + article.active_observation_count, 0),
)

const groupedArticles = computed(() => {
  const groups: { source: string; items: FashionArticleAdmin[] }[] = []
  const indexBySource = new Map<string, number>()
  for (const article of articles.value) {
    const source = article.source_name || '其他來源'
    if (!indexBySource.has(source)) {
      indexBySource.set(source, groups.length)
      groups.push({ source, items: [] })
    }
    groups[indexBySource.get(source)!].items.push(article)
  }
  return groups
})

const signalLabels: Record<string, string> = {
  timeless: '長期適用',
  current_trend: '當季流行',
  editorial_example: '示範案例',
}
function signalLabel(signal: string) {
  return signalLabels[signal] ?? signal
}

function retryFailed() {
  urlInput.value = collectResults.value
    .filter(result => result.status === 'failed' || result.status === 'unsupported')
    .map(result => (result.category ? '# ' + result.category + '\n' : '') + result.url)
    .join('\n')
  void collectUrls()
}

function formatDate(value: string | null) {
  if (!value) return '日期不明'
  return new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium' }).format(new Date(value))
}

function tags(article: FashionArticleAdmin) {
  return [...new Set(article.observations.flatMap(observation => [
    ...observation.audiences, ...observation.occasions,
    ...observation.styles, ...observation.garments,
  ]))].slice(0, 8)
}

function observationTags(observation: FashionArticleAdmin['observations'][number]) {
  return [...new Set([
    ...observation.audiences, ...observation.occasions, ...observation.climates,
    ...observation.seasons, ...observation.times_of_day, ...observation.formalities, ...observation.activities,
    ...observation.styles, ...observation.garments, ...observation.colors,
    ...observation.materials, ...observation.silhouettes, ...observation.styling_actions,
  ])]
}

async function loadArticles() {
  loading.value = true
  error.value = ''
  try {
    const response = await getFashionArticles(search.value)
    articles.value = response.items
    total.value = response.total
  } catch (reason) {
    articles.value = []
    total.value = 0
    error.value = reason instanceof Error ? reason.message : '無法讀取文章資料。'
  } finally {
    loading.value = false
  }
}

async function loadSources() {
  try {
    sources.value = await getFashionKnowledgeSources()
    selectedSourceKeys.value = sources.value.map(source => source.key)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '無法讀取自動更新來源。'
  }
}

function toggleExpanded(id: number) {
  const next = new Set(expandedIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  expandedIds.value = next
}

async function collectUrls(urls: string[] = [], forceRefresh = false) {
  const rawText = urls.length ? '' : urlInput.value
  if (!urls.length && !rawText.trim()) {
    error.value = '請輸入至少一個文章網址。'
    return
  }
  collecting.value = true
  error.value = ''
  notice.value = '正在匯入文章…'
  collectResults.value = []
  try {
    const response = await collectFashionArticles(urls, rawText, forceRefresh)
    collectResults.value = response.results
    notice.value = `成功匯入 ${response.succeeded}；略過 ${response.skipped}；網域未開放 ${response.unsupported}；抓取或整理失敗 ${response.failed}。`
    if (!response.failed && !response.unsupported) urlInput.value = ''
    await loadArticles()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '文章抓取失敗。'
    notice.value = ''
  } finally {
    collecting.value = false
  }
}

async function autoUpdate() {
  if (!selectedSourceKeys.value.length) {
    error.value = '請至少選擇一個文章來源。'
    return
  }
  collecting.value = true
  error.value = ''
  notice.value = '正在更新文章…'
  collectResults.value = []
  discoveryErrors.value = {}
  try {
    const response = await autoUpdateFashionArticles(
      selectedSourceKeys.value,
      perSourceLimit.value,
      pageLimit.value,
    )
    collectResults.value = response.results
    discoveryErrors.value = response.discovery_errors
    notice.value = response.discovered
      ? `發現 ${response.discovered} 篇未收錄文章；${response.succeeded} 篇成功，${response.failed} 篇失敗。`
      : `已檢查最新文章，目前沒有尚未收錄的內容（略過 ${response.skipped_existing} 個既有連結）。`
    await loadArticles()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '自動更新失敗。'
    notice.value = ''
  } finally {
    collecting.value = false
  }
}

async function refreshArticle(article: FashionArticleAdmin) {
  if (!window.confirm(`重新抓取「${article.title}」並取代原本的參考句子？`)) return
  await collectUrls([article.source_url], true)
  expandedIds.value = new Set([...expandedIds.value, article.id])
}

async function removeArticle(article: FashionArticleAdmin) {
  if (!window.confirm(`確定刪除「${article.title}」及其 ${article.observation_count} 條參考句子？`)) return
  error.value = ''
  try {
    await deleteFashionArticle(article.id)
    notice.value = '文章與相關參考句子已刪除。'
    await loadArticles()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '刪除失敗。'
  }
}

async function toggleObservation(article: FashionArticleAdmin, observationId: number, active: boolean) {
  try {
    await setFashionObservationActive(observationId, active)
    const observation = article.observations.find(item => item.id === observationId)
    if (observation) observation.is_active = active
    article.active_observation_count = article.observations.filter(item => item.is_active).length
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '更新參考句子失敗。'
  }
}

onMounted(() => Promise.all([loadArticles(), loadSources()]))
</script>

<template>
  <section class="page-view knowledge-view">
    <header class="view-heading knowledge-heading">
      <div>
        <span class="section-kicker">Knowledge Library</span>
        <h2>文章與搭配知識</h2>
        <p>{{ total }} 篇文章 · {{ activeObservationTotal }}/{{ observationTotal }} 條參考句子啟用中</p>
      </div>
      <div class="catalog-search">
        <Search :size="17" />
        <input v-model="search" placeholder="語意搜尋標題或知識，例如：女團造型、短上衣配寬褲" @keyup.enter="loadArticles" />
      </div>
    </header>

    <section class="knowledge-import-card">
      <details class="knowledge-import-details">
        <summary class="knowledge-import-summary">
          <RefreshCw :size="18" />
          <span>
            <strong>搜尋新文章</strong>
            <small>從常用穿搭網站自動找出尚未收錄的文章</small>
          </span>
        </summary>

        <div class="knowledge-import-body">
          <div class="knowledge-source-grid">
            <label v-for="source in sources" :key="source.key" class="knowledge-source-option">
              <input v-model="selectedSourceKeys" type="checkbox" :value="source.key" />
              <span><strong>{{ source.name }}</strong><small>{{ source.audience === 'women' ? '女裝' : '男裝' }}</small></span>
            </label>
          </div>

          <details class="knowledge-advanced">
            <summary>進階選項</summary>
            <div class="knowledge-import-actions">
              <label class="knowledge-limit-control">
                檢查列表頁數
                <select v-model.number="pageLimit">
                  <option :value="0">自動（直到沒有新連結）</option>
                  <option :value="1">1 頁</option>
                  <option :value="2">2 頁</option>
                  <option :value="3">3 頁</option>
                  <option :value="5">5 頁</option>
                  <option :value="10">10 頁</option>
                </select>
              </label>
              <label class="knowledge-limit-control">
                每個來源最多
                <select v-model.number="perSourceLimit">
                  <option :value="1">1 篇</option>
                  <option :value="2">2 篇</option>
                  <option :value="3">3 篇</option>
                </select>
              </label>
            </div>
          </details>

          <button class="primary-button" :disabled="collecting || !sources.length" @click="autoUpdate">
            <LoaderCircle v-if="collecting" class="spinning" :size="16" />
            <RefreshCw v-else :size="16" />
            {{ collecting ? '更新中…' : '檢查並抓取新文章' }}
          </button>

          <details class="manual-import">
            <summary>手動補抓特定文章（選用）</summary>
            <textarea v-model="urlInput" rows="3" placeholder="可貼上 Markdown 分類標題、文章連結或每行一個網址" />
            <button class="secondary-button" :disabled="collecting" @click="collectUrls()">
              <Plus :size="15" />抓取指定網址
            </button>
          </details>
        </div>
      </details>
    </section>

    <p v-if="error" class="error-banner">{{ error }}</p>
    <p v-if="notice" class="success-banner">{{ notice }}</p>
    <ul v-if="Object.keys(discoveryErrors).length" class="discovery-errors">
      <li v-for="(message, key) in discoveryErrors" :key="key"><strong>{{ key }}</strong>：{{ message }}</li>
    </ul>
    <ul v-if="collectResults.length" class="collect-results">
      <li v-for="result in collectResults" :key="result.url" :class="result.status">
        <strong>{{ result.status === 'skipped' ? '略過' : result.status === 'unsupported' ? '網域未開放' : result.status === 'failed' ? '失敗' : result.status === 'updated' ? '已更新' : '已新增' }}</strong>
        <small v-if="result.category">分類：{{ result.category }}</small>
        <span>{{ result.title || '文章處理失敗' }}</span>
        <a v-if="result.status !== 'skipped'" :href="result.url" target="_blank" rel="noopener noreferrer">{{ result.url }}</a>
        <span v-else>{{ result.url }}</span>
        <small>{{ result.message }}<template v-if="result.observation_count"> · {{ result.observation_count }} 條</template></small>
      </li>
    </ul>
    <button v-if="collectResults.some(result => result.status === 'failed' || result.status === 'unsupported')"
      class="secondary-button" :disabled="collecting"
      @click="retryFailed">
      <RefreshCw :size="15" />只重試網域未開放與抓取失敗的文章
    </button>

    <div class="knowledge-toolbar">
      <button class="secondary-button" :disabled="loading" @click="loadArticles">
        <RefreshCw :class="{ spinning: loading }" :size="15" />重新整理
      </button>
    </div>

    <div v-if="loading && !articles.length" class="loading-state">
      <LoaderCircle class="spinning" :size="28" />正在載入文章知識…
    </div>
    <div v-else-if="!articles.length" class="empty-view">
      <BookOpenText :size="34" />
      <h3>目前沒有符合的文章</h3>
    </div>
    <div v-else class="knowledge-article-groups">
      <section v-for="group in groupedArticles" :key="group.source" class="knowledge-article-group">
        <h3 class="knowledge-group-title">{{ group.source }}<small>{{ group.items.length }} 篇</small></h3>
        <div class="knowledge-article-list">
          <article v-for="article in group.items" :key="article.id" class="knowledge-article-card">
            <div class="knowledge-article-main">
              <button class="knowledge-expand-button" @click="toggleExpanded(article.id)">
                <ChevronDown :class="{ expanded: expandedIds.has(article.id) }" :size="18" />
              </button>
              <div class="knowledge-article-content">
                <div class="knowledge-article-meta">
                  <span>{{ formatDate(article.published_at || article.collected_at) }}</span>
                  <span>{{ article.active_observation_count }}/{{ article.observation_count }} 條啟用</span>
                </div>
                <h3>
                  <a class="knowledge-article-title" :href="article.source_url" target="_blank" rel="noopener noreferrer">
                    {{ article.title }} <ExternalLink :size="14" />
                  </a>
                </h3>
                <small v-for="category in article.extraction_notes.filter(note => note.startsWith('匯入分類：'))" :key="category">{{ category }}</small>
                <p v-if="article.search_match_kind">
                  {{ article.search_match_kind === 'knowledge' ? '命中內容重點' : '命中標題或摘要' }}
                  <br />{{ article.search_match_text }}
                </p>
                <p v-if="expandedIds.has(article.id)">{{ article.article_summary }}</p>
                <div v-if="expandedIds.has(article.id)" class="knowledge-tags">
                  <span v-for="tag in tags(article)" :key="tag">{{ tag }}</span>
                </div>
              </div>
              <div class="knowledge-card-actions">
                <button class="icon-button" :disabled="collecting" title="重新抓取" @click="refreshArticle(article)"><RefreshCw :size="15" /></button>
                <button class="icon-button danger" title="刪除文章" @click="removeArticle(article)"><Trash2 :size="15" /></button>
              </div>
            </div>

            <div v-if="expandedIds.has(article.id)" class="knowledge-observations">
              <div class="knowledge-observations-heading">
                <strong>這篇文章存下的參考句子</strong>
              </div>
              <div v-for="(observation, index) in article.observations" :key="observation.id"
                class="knowledge-observation" :class="{ inactive: !observation.is_active }">
                <div class="observation-number">{{ index + 1 }}</div>
                <div>
                  <strong>{{ observation.summary }}</strong>
                  <p>依據：{{ observation.evidence }}</p>
                  <div class="knowledge-tags compact">
                    <span>{{ signalLabel(observation.signal_type) }}</span>
                    <span v-for="tag in observationTags(observation)" :key="tag">{{ tag }}</span>
                  </div>
                </div>
                <label class="knowledge-switch">
                  <input type="checkbox" :checked="observation.is_active"
                    @change="toggleObservation(article, observation.id, ($event.target as HTMLInputElement).checked)" />
                  <span>{{ observation.is_active ? '啟用' : '停用' }}</span>
                </label>
              </div>
            </div>
          </article>
        </div>
      </section>
    </div>
  </section>
</template>
