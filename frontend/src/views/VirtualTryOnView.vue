<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { AlertCircle, CheckCircle2, ImagePlus, LoaderCircle, RefreshCw, ScanFace, Trash2 } from 'lucide-vue-next'
import { createTryOnJob, getTryOnCapabilities, getTryOnJob } from '../api'
import type { TryOnCapabilities, TryOnClothType, TryOnJob } from '../types'

const props = defineProps<{ userKey: string }>()

const HISTORY_STORAGE_VERSION = 1
const HISTORY_LIMIT = 20
const JOB_STATUSES = ['queued', 'running', 'succeeded', 'failed'] as const
const CLOTH_TYPES = ['upper', 'lower', 'overall'] as const

interface StoredTryOnHistory {
  version: typeof HISTORY_STORAGE_VERSION
  selectedJobId: string | null
  jobs: TryOnJob[]
}

const capabilities = ref<TryOnCapabilities | null>(null)
const capabilityLoading = ref(true)
const personFile = ref<File | null>(null)
const clothFile = ref<File | null>(null)
const personPreview = ref('')
const clothPreview = ref('')
const clothType = ref<TryOnClothType>('upper')
const job = ref<TryOnJob | null>(null)
const historyJobs = ref<TryOnJob[]>([])
const historySyncError = ref('')
const submitting = ref(false)
const error = ref('')
let pollTimer: number | undefined
let cleanupTimer: number | undefined
let componentActive = false
let historyGeneration = 0
const retryJobIds = new Set<string>()

const historyStorageKey = computed(() => `matching-outfit.tryon-history:v1:${props.userKey}`)

const canSubmit = computed(() => (
  capabilities.value?.available
  && personFile.value
  && clothFile.value
  && !submitting.value
  && !['queued', 'running'].includes(job.value?.status ?? '')
))

const statusLabel = computed(() => {
  if (!job.value) return ''
  return {
    queued: '等待 GPU 處理',
    running: '正在產生試穿結果',
    succeeded: '試穿完成',
    failed: '試穿失敗',
  }[job.value.status]
})

function stopPolling() {
  if (pollTimer !== undefined) window.clearTimeout(pollTimer)
  pollTimer = undefined
}

function isTryOnJob(value: unknown): value is TryOnJob {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === 'string'
    && JOB_STATUSES.includes(candidate.status as TryOnJob['status'])
    && CLOTH_TYPES.includes(candidate.cloth_type as TryOnClothType)
    && (candidate.error === null || typeof candidate.error === 'string')
    && (candidate.result_url === null || typeof candidate.result_url === 'string')
    && typeof candidate.created_at === 'string'
    && typeof candidate.updated_at === 'string'
    && (candidate.expires_at === null || typeof candidate.expires_at === 'string')
    && Number.isFinite(Date.parse(candidate.created_at))
    && Number.isFinite(Date.parse(candidate.updated_at))
    && (candidate.expires_at === null || Number.isFinite(Date.parse(candidate.expires_at)))
  )
}

function isExpired(historyJob: TryOnJob) {
  if (!historyJob.expires_at) return false
  const expiresAt = Date.parse(historyJob.expires_at)
  return Number.isFinite(expiresAt) && expiresAt <= Date.now()
}

function sortAndLimitHistory(jobs: TryOnJob[]) {
  const uniqueJobs = jobs.filter((historyJob, index) => (
    jobs.findIndex((candidate) => candidate.id === historyJob.id) === index
  ))
  return uniqueJobs
    .filter((historyJob) => !isExpired(historyJob))
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
    .slice(0, HISTORY_LIMIT)
}

function persistHistory() {
  try {
    if (!historyJobs.value.length) {
      window.localStorage.removeItem(historyStorageKey.value)
      return
    }
    const payload: StoredTryOnHistory = {
      version: HISTORY_STORAGE_VERSION,
      selectedJobId: job.value?.id ?? null,
      jobs: historyJobs.value,
    }
    window.localStorage.setItem(historyStorageKey.value, JSON.stringify(payload))
  } catch {
    historySyncError.value = '瀏覽器無法保存最近試穿紀錄。'
  }
}

function discardStoredHistory() {
  try {
    window.localStorage.removeItem(historyStorageKey.value)
  } catch {
    // Browsers may deny storage access; the in-memory view can still be used.
  }
}

function selectHistoryJob(historyJob: TryOnJob) {
  job.value = historyJob
  error.value = historyJob.status === 'failed' ? historyJob.error || '試穿工作失敗' : ''
  persistHistory()
}

function replaceHistory(nextJob: TryOnJob, select = false) {
  historyJobs.value = sortAndLimitHistory([
    nextJob,
    ...historyJobs.value.filter((historyJob) => historyJob.id !== nextJob.id),
  ])
  if (select || job.value?.id === nextJob.id) job.value = nextJob
  if (!job.value && historyJobs.value.length) job.value = historyJobs.value[0]
  persistHistory()
}

function cleanExpiredHistory() {
  const currentIds = historyJobs.value.map((historyJob) => historyJob.id)
  historyJobs.value = sortAndLimitHistory(historyJobs.value)
  const changed = historyJobs.value.length !== currentIds.length
    || historyJobs.value.some((historyJob, index) => historyJob.id !== currentIds[index])
  if (job.value && !historyJobs.value.some((historyJob) => historyJob.id === job.value?.id)) {
    job.value = historyJobs.value[0] ?? null
  }
  if (changed) persistHistory()
}

function loadHistory() {
  try {
    const raw = window.localStorage.getItem(historyStorageKey.value)
    if (!raw) return
    const stored = JSON.parse(raw) as Partial<StoredTryOnHistory>
    if (stored.version !== HISTORY_STORAGE_VERSION || !Array.isArray(stored.jobs)) {
      discardStoredHistory()
      return
    }
    historyJobs.value = sortAndLimitHistory(stored.jobs.filter(isTryOnJob))
    job.value = historyJobs.value.find((historyJob) => historyJob.id === stored.selectedJobId)
      ?? historyJobs.value[0]
      ?? null
    persistHistory()
  } catch {
    discardStoredHistory()
  }
}

function clearHistory() {
  if (!window.confirm('清除這個瀏覽器中的最近試穿紀錄？遠端工作不會刪除，但之後將無法從此列表找回。')) return
  stopPolling()
  historyGeneration += 1
  retryJobIds.clear()
  historyJobs.value = []
  historySyncError.value = ''
  job.value = null
  error.value = ''
  discardStoredHistory()
}

function clothTypeLabel(type: TryOnClothType) {
  return { upper: '上身', lower: '下身', overall: '洋裝／連身' }[type]
}

function historyStatusLabel(status: TryOnJob['status']) {
  return { queued: '排隊中', running: '處理中', succeeded: '已完成', failed: '失敗' }[status]
}

function formatHistoryTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-TW', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function replacePreview(current: string, file: File | null) {
  if (current) URL.revokeObjectURL(current)
  return file ? URL.createObjectURL(file) : ''
}

function chooseImage(event: Event, kind: 'person' | 'cloth') {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (kind === 'person') {
    personPreview.value = replacePreview(personPreview.value, file)
    personFile.value = file
  } else {
    clothPreview.value = replacePreview(clothPreview.value, file)
    clothFile.value = file
  }
  error.value = ''
}

async function loadCapabilities() {
  capabilityLoading.value = true
  error.value = ''
  try {
    capabilities.value = await getTryOnCapabilities()
  } catch (reason) {
    capabilities.value = null
    error.value = reason instanceof Error ? reason.message : '無法檢查 CatVTON 狀態'
  } finally {
    capabilityLoading.value = false
  }
}

async function synchronizeHistory(refreshAll = false) {
  stopPolling()
  cleanExpiredHistory()
  if (!historyJobs.value.length) return

  const generation = historyGeneration
  const jobsToSynchronize = historyJobs.value.filter((historyJob) => (
    refreshAll
    || historyJob.status === 'queued'
    || historyJob.status === 'running'
    || retryJobIds.has(historyJob.id)
  ))
  if (!jobsToSynchronize.length) return
  const results = await Promise.allSettled(
    jobsToSynchronize.map((historyJob) => getTryOnJob(historyJob.id)),
  )
  if (!componentActive || generation !== historyGeneration) return

  let failedRequests = 0
  results.forEach((result, resultIndex) => {
    const synchronizedJobId = jobsToSynchronize[resultIndex].id
    if (result.status === 'fulfilled') {
      retryJobIds.delete(synchronizedJobId)
      const index = historyJobs.value.findIndex((historyJob) => historyJob.id === result.value.id)
      if (index >= 0) historyJobs.value[index] = result.value
      if (job.value?.id === result.value.id) job.value = result.value
    } else {
      retryJobIds.add(synchronizedJobId)
      failedRequests += 1
    }
  })

  historyJobs.value = sortAndLimitHistory(historyJobs.value)
  if (job.value && !historyJobs.value.some((historyJob) => historyJob.id === job.value?.id)) {
    job.value = historyJobs.value[0] ?? null
  }
  persistHistory()

  historySyncError.value = failedRequests
    ? `有 ${failedRequests} 筆紀錄暫時無法更新，將自動重試。`
    : ''
  if (job.value?.status === 'failed') error.value = job.value.error || '試穿工作失敗'

  const hasPendingJobs = historyJobs.value.some(
    (historyJob) => historyJob.status === 'queued' || historyJob.status === 'running',
  )
  if (hasPendingJobs || failedRequests) {
    pollTimer = window.setTimeout(synchronizeHistory, failedRequests ? 5000 : 2000)
  }
}

async function submit() {
  if (!canSubmit.value || !personFile.value || !clothFile.value) return
  stopPolling()
  submitting.value = true
  error.value = ''
  try {
    const createdJob = await createTryOnJob(
      personFile.value,
      clothFile.value,
      clothType.value,
      props.userKey,
    )
    replaceHistory(createdJob, true)
    pollTimer = window.setTimeout(synchronizeHistory, 2000)
  } catch (reason) {
    const submitError = reason instanceof Error ? reason.message : '無法建立試穿工作'
    await loadCapabilities()
    error.value = submitError
  } finally {
    submitting.value = false
    const hasPendingJobs = historyJobs.value.some(
      (historyJob) => historyJob.status === 'queued' || historyJob.status === 'running',
    )
    if (pollTimer === undefined && (hasPendingJobs || retryJobIds.size)) {
      pollTimer = window.setTimeout(synchronizeHistory, 2000)
    }
  }
}

onMounted(() => {
  componentActive = true
  loadHistory()
  void loadCapabilities()
  void synchronizeHistory(true)
  cleanupTimer = window.setInterval(cleanExpiredHistory, 60_000)
})
onBeforeUnmount(() => {
  componentActive = false
  stopPolling()
  if (cleanupTimer !== undefined) window.clearInterval(cleanupTimer)
  if (personPreview.value) URL.revokeObjectURL(personPreview.value)
  if (clothPreview.value) URL.revokeObjectURL(clothPreview.value)
})
</script>

<template>
  <section class="page-view tryon-view">
    <header class="view-heading">
      <div>
        <span class="section-kicker">Virtual try-on</span>
        <h2>虛擬試穿</h2>
        <p>上傳全身人物照與單件衣服圖片，使用 CatVTON 產生試穿預覽。</p>
      </div>
      <button class="secondary-button" :disabled="capabilityLoading" @click="loadCapabilities">
        <RefreshCw :size="16" :class="{ spinning: capabilityLoading }" />重新檢查服務
      </button>
    </header>

    <div
      v-if="!capabilityLoading && !capabilities?.available"
      class="tryon-service-banner unavailable"
      role="status"
    >
      <AlertCircle :size="19" />
      <div><strong>CatVTON 尚未連線</strong><p>{{ capabilities?.reason || 'GPU 推論服務目前無法使用' }}</p></div>
    </div>
    <div v-else-if="capabilities?.available" class="tryon-service-banner available" role="status">
      <CheckCircle2 :size="19" />
      <div><strong>CatVTON 已就緒</strong><p>圖片會在工作結束後刪除；結果保留 24 小時，可從此瀏覽器的最近試穿紀錄找回。</p></div>
    </div>

    <div class="tryon-layout">
      <section class="tryon-form-card">
        <div class="tryon-upload-grid">
          <label class="tryon-upload">
            <span>1 · 人物照片</span>
            <div class="tryon-preview">
              <img v-if="personPreview" :src="personPreview" alt="人物照片預覽" />
              <div v-else><ImagePlus :size="30" /><strong>選擇人物照片</strong><small>建議使用正面全身照</small></div>
            </div>
            <input type="file" accept="image/jpeg,image/png,image/webp" @change="chooseImage($event, 'person')" />
          </label>

          <label class="tryon-upload">
            <span>2 · 衣服圖片</span>
            <div class="tryon-preview">
              <img v-if="clothPreview" :src="clothPreview" alt="衣服圖片預覽" />
              <div v-else><ImagePlus :size="30" /><strong>選擇衣服圖片</strong><small>建議使用乾淨背景商品照</small></div>
            </div>
            <input type="file" accept="image/jpeg,image/png,image/webp" @change="chooseImage($event, 'cloth')" />
          </label>
        </div>

        <fieldset class="tryon-type-field">
          <legend>3 · 試穿類型</legend>
          <div class="segmented-control">
            <button type="button" :class="{ active: clothType === 'upper' }" @click="clothType = 'upper'">上身</button>
            <button type="button" :class="{ active: clothType === 'lower' }" @click="clothType = 'lower'">下身</button>
            <button type="button" :class="{ active: clothType === 'overall' }" @click="clothType = 'overall'">洋裝／連身</button>
          </div>
        </fieldset>

        <p v-if="error" class="error-banner">{{ error }}</p>
        <button class="primary-button tryon-submit" :disabled="!canSubmit" @click="submit">
          <LoaderCircle v-if="submitting" :size="17" class="spinning" />
          <ScanFace v-else :size="17" />
          {{ submitting ? '建立工作中…' : '開始虛擬試穿' }}
        </button>
        <p class="tryon-limit">每張圖片上限 {{ Math.round((capabilities?.max_upload_bytes || 10485760) / 1048576) }} MiB</p>
      </section>

      <section class="tryon-result-card">
        <div v-if="historyJobs.length" class="tryon-history">
          <div class="tryon-history-heading">
            <div><strong>最近試穿</strong><small>僅保存在此瀏覽器；清除後不會刪除遠端工作</small></div>
            <button type="button" title="只清除本機紀錄，不會刪除遠端工作" @click="clearHistory">
              <Trash2 :size="14" />清除本機紀錄
            </button>
          </div>
          <div class="tryon-history-list" role="list" aria-label="最近試穿紀錄">
            <button
              v-for="historyJob in historyJobs"
              :key="historyJob.id"
              type="button"
              role="listitem"
              :aria-pressed="job?.id === historyJob.id"
              :class="['tryon-history-item', historyJob.status, { active: job?.id === historyJob.id }]"
              @click="selectHistoryJob(historyJob)"
            >
              <span>{{ historyStatusLabel(historyJob.status) }}</span>
              <strong>{{ clothTypeLabel(historyJob.cloth_type) }}</strong>
              <small>{{ formatHistoryTime(historyJob.created_at) }}</small>
            </button>
          </div>
          <p v-if="historySyncError" class="tryon-history-error">{{ historySyncError }}</p>
        </div>
        <div class="tryon-result-body">
          <div v-if="job?.status === 'succeeded' && job.result_url" class="tryon-result">
            <img :src="job.result_url" alt="CatVTON 虛擬試穿結果" />
            <div><CheckCircle2 :size="17" /><strong>{{ statusLabel }}</strong></div>
          </div>
          <div v-else class="tryon-result-placeholder" :class="{ processing: job?.status === 'queued' || job?.status === 'running' }">
            <LoaderCircle v-if="job?.status === 'queued' || job?.status === 'running'" :size="36" class="spinning" />
            <ScanFace v-else :size="42" />
            <h3>{{ statusLabel || '試穿結果會顯示在這裡' }}</h3>
            <p v-if="job?.status === 'queued'">GPU 同一時間處理一個工作，可安心離開後再回來查看。</p>
            <p v-else-if="job?.status === 'running'">生成通常需要數十秒，可安心離開後再回來查看。</p>
            <p v-else-if="job?.status === 'failed'">{{ job.error || '這次試穿未能完成，請重新送出。' }}</p>
            <p v-else>準備好兩張圖片並連接 GPU 服務後即可開始。</p>
          </div>
        </div>
      </section>
    </div>

    <p class="tryon-attribution">
      Powered by CatVTON · CC BY-NC-SA 4.0 · 僅供非商業用途
    </p>
  </section>
</template>
