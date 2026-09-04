<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { AlertCircle, CheckCircle2, ImagePlus, LoaderCircle, RefreshCw, ScanFace, Trash2 } from 'lucide-vue-next'
import { createTryOnJob, getTryOnCapabilities, getTryOnJob } from '../api'
import type { TryOnCapabilities, TryOnJob, TryOnReferenceType } from '../types'

const props = defineProps<{ userKey: string }>()

const HISTORY_STORAGE_VERSION = 2
const HISTORY_LIMIT = 20
const JOB_STATUSES = ['queued', 'running', 'succeeded', 'failed'] as const
const REFERENCE_TYPES = ['upper', 'lower', 'overall', 'shoe', 'bag'] as const satisfies readonly TryOnReferenceType[]
const REFERENCE_LABELS: Record<TryOnReferenceType, string> = {
  upper: '上身',
  lower: '下身',
  overall: '洋裝／連身',
  shoe: '鞋子',
  bag: '包包',
}
const REFERENCE_OPTIONS: { type: TryOnReferenceType; hint: string }[] = [
  { type: 'upper', hint: '上衣、外套等商品照' },
  { type: 'lower', hint: '褲子、裙子等商品照' },
  { type: 'overall', hint: '洋裝或連身服飾商品照' },
  { type: 'shoe', hint: '鞋款商品照' },
  { type: 'bag', hint: '包款商品照' },
]

interface StoredTryOnHistory {
  version: typeof HISTORY_STORAGE_VERSION
  selectedJobId: string | null
  jobs: TryOnJob[]
}

const capabilities = ref<TryOnCapabilities | null>(null)
const capabilityLoading = ref(true)
const personFile = ref<File | null>(null)
const personPreview = ref('')
const referenceFiles = ref<Partial<Record<TryOnReferenceType, File>>>({})
const referencePreviews = ref<Partial<Record<TryOnReferenceType, string>>>({})
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

const historyStorageKey = computed(() => `matching-outfit.tryon-history:v2:${props.userKey}`)
const legacyHistoryStorageKey = computed(() => `matching-outfit.tryon-history:v1:${props.userKey}`)
const selectedReferenceTypes = computed(() => (
  REFERENCE_TYPES.filter((referenceType) => Boolean(referenceFiles.value[referenceType]))
))
const selectedReferencesAreCompatible = computed(() => !(
  referenceFiles.value.overall
  && (referenceFiles.value.upper || referenceFiles.value.lower)
))
const selectedReferencesAreSupported = computed(() => selectedReferenceTypes.value.every(
  (referenceType) => capabilities.value?.supported_reference_types.includes(referenceType),
))

const canSubmit = computed(() => (
  capabilities.value?.available
  && personFile.value
  && selectedReferenceTypes.value.length > 0
  && selectedReferencesAreCompatible.value
  && selectedReferencesAreSupported.value
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
    && Array.isArray(candidate.reference_types)
    && candidate.reference_types.length > 0
    && candidate.reference_types.every((type) => REFERENCE_TYPES.includes(type as TryOnReferenceType))
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
    window.localStorage.removeItem(legacyHistoryStorageKey.value)
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

function referenceTypesLabel(types: TryOnReferenceType[]) {
  return types.map((type) => REFERENCE_LABELS[type]).join('、')
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

function choosePersonImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  personPreview.value = replacePreview(personPreview.value, file)
  personFile.value = file
  error.value = ''
}

function removePersonImage() {
  personPreview.value = replacePreview(personPreview.value, null)
  personFile.value = null
  error.value = ''
}

function chooseReferenceImage(event: Event, referenceType: TryOnReferenceType) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (!file) {
    removeReferenceImage(referenceType)
    return
  }
  const currentPreview = referencePreviews.value[referenceType] ?? ''
  referencePreviews.value = {
    ...referencePreviews.value,
    [referenceType]: replacePreview(currentPreview, file),
  }
  referenceFiles.value = { ...referenceFiles.value, [referenceType]: file }
  error.value = ''
}

function removeReferenceImage(referenceType: TryOnReferenceType) {
  const preview = referencePreviews.value[referenceType]
  if (preview) URL.revokeObjectURL(preview)
  const nextPreviews = { ...referencePreviews.value }
  const nextFiles = { ...referenceFiles.value }
  delete nextPreviews[referenceType]
  delete nextFiles[referenceType]
  referencePreviews.value = nextPreviews
  referenceFiles.value = nextFiles
  error.value = ''
}

function isReferenceDisabled(referenceType: TryOnReferenceType) {
  const supportedTypes = capabilities.value?.supported_reference_types
  if (supportedTypes && !supportedTypes.includes(referenceType)) return true
  if ((referenceType === 'upper' || referenceType === 'lower') && referenceFiles.value.overall) return true
  return referenceType === 'overall' && Boolean(referenceFiles.value.upper || referenceFiles.value.lower)
}

function referenceDisabledReason(referenceType: TryOnReferenceType) {
  if (capabilities.value && !capabilities.value.supported_reference_types.includes(referenceType)) {
    return '目前服務不支援此類型'
  }
  if (referenceType === 'overall') return '已選擇上身或下身圖片'
  return '已選擇洋裝／連身圖片'
}

function referenceInputKey(referenceType: TryOnReferenceType) {
  const file = referenceFiles.value[referenceType]
  return file ? `${file.name}:${file.size}:${file.lastModified}` : `${referenceType}:empty`
}

function personInputKey() {
  const file = personFile.value
  return file ? `${file.name}:${file.size}:${file.lastModified}` : 'person:empty'
}

function referencePreview(referenceType: TryOnReferenceType) {
  return referencePreviews.value[referenceType] ?? ''
}

function referenceFile(referenceType: TryOnReferenceType) {
  return referenceFiles.value[referenceType]
}

function referenceLabel(referenceType: TryOnReferenceType) {
  return REFERENCE_LABELS[referenceType]
}

function referenceIsSelected(referenceType: TryOnReferenceType) {
  return Boolean(referenceFiles.value[referenceType])
}

async function loadCapabilities() {
  capabilityLoading.value = true
  error.value = ''
  try {
    capabilities.value = await getTryOnCapabilities()
  } catch (reason) {
    capabilities.value = null
    error.value = reason instanceof Error ? reason.message : '無法檢查試穿服務狀態'
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
  if (!canSubmit.value || !personFile.value) return
  stopPolling()
  submitting.value = true
  error.value = ''
  try {
    const createdJob = await createTryOnJob(
      personFile.value,
      referenceFiles.value,
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
  Object.values(referencePreviews.value).forEach((preview) => {
    if (preview) URL.revokeObjectURL(preview)
  })
})
</script>

<template>
  <section class="page-view tryon-view">
    <header class="view-heading">
      <div>
        <span class="section-kicker">Virtual try-on</span>
        <h2>虛擬試穿</h2>
        <p>上傳全身人物照與服飾參考圖片，一次預覽完整搭配。</p>
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
      <div><strong>試穿服務尚未連線</strong><p>{{ capabilities?.reason || 'GPU 推論服務目前無法使用' }}</p></div>
    </div>
    <div v-else-if="capabilities?.available" class="tryon-service-banner available" role="status">
      <CheckCircle2 :size="19" />
      <div><strong>試穿服務已就緒</strong><p>圖片會在工作結束後刪除；結果保留 24 小時，可從此瀏覽器的最近試穿紀錄找回。</p></div>
    </div>

    <div class="tryon-layout">
      <section class="tryon-form-card">
        <section class="tryon-upload-section">
          <div class="tryon-upload tryon-person-upload">
            <span>人物照片</span>
            <label class="tryon-preview tryon-preview-input">
              <img v-if="personPreview" :src="personPreview" alt="人物照片預覽" />
              <span v-else class="tryon-preview-copy"><ImagePlus :size="30" /><strong>選擇人物照片</strong><small>建議使用正面全身照</small></span>
              <input
                :key="personInputKey()"
                class="tryon-file-input"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                :aria-label="`${personFile ? '更換圖片' : '選擇圖片'}：人物照片`"
                @change="choosePersonImage"
              />
            </label>
            <div class="tryon-upload-actions">
              <button
                v-if="personFile"
                type="button"
                class="tryon-remove-button"
                aria-label="移除人物照片"
                @click="removePersonImage"
              >
                <Trash2 :size="13" />移除
              </button>
            </div>
          </div>
        </section>

        <section class="tryon-upload-section tryon-reference-section">
          <div class="tryon-section-heading">
            <strong>服飾參考圖片</strong>
            <small>至少選擇一項；洋裝／連身不可與上身或下身同時使用</small>
          </div>
          <div class="tryon-reference-grid">
            <div
              v-for="option in REFERENCE_OPTIONS"
              :key="option.type"
              class="tryon-upload"
              :class="{ disabled: isReferenceDisabled(option.type) }"
            >
              <span>{{ referenceLabel(option.type) }}</span>
              <label
                class="tryon-preview tryon-preview-input"
                :aria-disabled="isReferenceDisabled(option.type)"
              >
                <img
                  v-if="referencePreview(option.type)"
                  :src="referencePreview(option.type)"
                  :alt="`${referenceLabel(option.type)}參考圖片預覽`"
                />
                <span v-else class="tryon-preview-copy">
                  <ImagePlus :size="26" />
                  <strong>選擇{{ referenceLabel(option.type) }}圖片</strong>
                  <small>{{ isReferenceDisabled(option.type) ? referenceDisabledReason(option.type) : option.hint }}</small>
                </span>
                <input
                  :key="referenceInputKey(option.type)"
                  class="tryon-file-input"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  :disabled="isReferenceDisabled(option.type)"
                  :aria-label="`${referenceFile(option.type) ? '更換圖片' : '選擇圖片'}：${referenceLabel(option.type)}參考圖片`"
                  @change="chooseReferenceImage($event, option.type)"
                />
              </label>
              <div class="tryon-upload-actions">
                <button
                  v-if="referenceIsSelected(option.type)"
                  type="button"
                  class="tryon-remove-button"
                  :aria-label="`移除${referenceLabel(option.type)}參考圖片`"
                  @click="removeReferenceImage(option.type)"
                >
                  <Trash2 :size="13" />移除
                </button>
              </div>
            </div>
          </div>
        </section>

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
              <strong>{{ referenceTypesLabel(historyJob.reference_types) }}</strong>
              <small>{{ formatHistoryTime(historyJob.created_at) }}</small>
            </button>
          </div>
          <p v-if="historySyncError" class="tryon-history-error">{{ historySyncError }}</p>
        </div>
        <div class="tryon-result-body">
          <div v-if="job?.status === 'succeeded' && job.result_url" class="tryon-result">
            <img :src="job.result_url" alt="虛擬試穿結果" />
            <div><CheckCircle2 :size="17" /><strong>{{ statusLabel }}</strong></div>
          </div>
          <div v-else class="tryon-result-placeholder" :class="{ processing: job?.status === 'queued' || job?.status === 'running' }">
            <LoaderCircle v-if="job?.status === 'queued' || job?.status === 'running'" :size="36" class="spinning" />
            <ScanFace v-else :size="42" />
            <h3>{{ statusLabel || '試穿結果會顯示在這裡' }}</h3>
            <p v-if="job?.status === 'queued'">GPU 同一時間處理一個工作，可安心離開後再回來查看。</p>
            <p v-else-if="job?.status === 'running'">生成通常需要數十秒，可安心離開後再回來查看。</p>
            <p v-else-if="job?.status === 'failed'">{{ job.error || '這次試穿未能完成，請重新送出。' }}</p>
            <p v-else>準備好人物照片與至少一張參考圖片，並連接 GPU 服務後即可開始。</p>
          </div>
        </div>
      </section>
    </div>

  </section>
</template>
