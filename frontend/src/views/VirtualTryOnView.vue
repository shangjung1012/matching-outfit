<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AlertCircle,
  Box,
  Check,
  CheckCircle2,
  ImagePlus,
  Images,
  LoaderCircle,
  Pencil,
  RefreshCw,
  ScanFace,
  Shirt,
  Star,
  Trash2,
  Upload,
  X,
} from 'lucide-vue-next'
import {
  createHuman3DJob,
  createTryOnJob,
  getHuman3DCapabilities,
  getHuman3DJob,
  getTryOnCapabilities,
  getTryOnJob,
} from '../api'
import Human3DViewer from '../components/Human3DViewer.vue'
import { usePersonPhotoLibrary, PERSON_PHOTO_LIMIT, validatePersonPhoto } from '../composables/usePersonPhotoLibrary'
import { useToast } from '../composables/useToast'
import { useUserLibrary } from '../composables/useUserLibrary'
import type {
  CatalogItem,
  Human3DCapabilities,
  Human3DJob,
  SavedPersonPhoto,
  TryOnCapabilities,
  TryOnDraft,
  TryOnJob,
  TryOnReferenceSelection,
  TryOnReferenceType,
} from '../types'
import {
  createTryOnDraft,
  referenceTypeForCatalogItem,
  TRYON_REFERENCE_LABELS,
  TRYON_REFERENCE_TYPES,
} from '../utils/tryOnSelection'
import { canGenerateHuman3D, human3DStatusLabel } from '../utils/human3dUi'

const props = defineProps<{ userKey: string; draft: TryOnDraft | null }>()
const { showError } = useToast()

const HISTORY_STORAGE_VERSION = 2
const HISTORY_LIMIT = 20
const DEFAULT_MAX_BYTES = 10 * 1024 * 1024
const DEFAULT_MAX_PIXELS = 20_000_000
const JOB_STATUSES = ['queued', 'running', 'succeeded', 'failed'] as const
const WARDROBE_TABS = ['outfits', 'items', 'upload'] as const

interface StoredTryOnHistory {
  version: typeof HISTORY_STORAGE_VERSION
  selectedJobId: string | null
  jobs: TryOnJob[]
}

type WardrobeTab = 'outfits' | 'items' | 'upload'

const capabilities = ref<TryOnCapabilities | null>(null)
const capabilityLoading = ref(true)
const human3DCapabilities = ref<Human3DCapabilities | null>(null)
const human3DCapabilityLoading = ref(true)
const wardrobeTab = ref<WardrobeTab>('outfits')
const references = ref<Partial<Record<TryOnReferenceType, TryOnReferenceSelection>>>({})
const draftCandidates = ref<Partial<Record<TryOnReferenceType, CatalogItem[]>>>({})
const unsupportedItems = ref<CatalogItem[]>([])
const selectedPersonId = ref<string | null>(null)
const temporaryPersonFile = ref<File | null>(null)
const temporaryPersonPreview = ref('')
const personPreviewUrls = ref<Record<string, string>>({})
const newPhotoName = ref('')
const photoSaving = ref(false)
const photoError = ref('')
const editingPhotoId = ref<string | null>(null)
const editingPhotoName = ref('')
const job = ref<TryOnJob | null>(null)
const historyJobs = ref<TryOnJob[]>([])
const submitting = ref(false)
const human3DJob = ref<Human3DJob | null>(null)
const human3DSubmitting = ref(false)
const resultMode = ref<'2d' | '3d'>('2d')
let pollTimer: number | undefined
let human3DPollTimer: number | undefined
let cleanupTimer: number | undefined
let componentActive = false
let historyGeneration = 0
const retryJobIds = new Set<string>()

const personLibrary = usePersonPhotoLibrary(props.userKey)
const {
  favoriteItems,
  favoriteOutfits,
  favoritesLoading,
  loadFavorites,
} = useUserLibrary(props.userKey)

const historyStorageKey = computed(() => `matching-outfit.tryon-history:v2:${props.userKey}`)
const legacyHistoryStorageKey = computed(() => `matching-outfit.tryon-history:v1:${props.userKey}`)
const selectedSavedPerson = computed(() => (
  personLibrary.photos.value.find((photo) => photo.id === selectedPersonId.value) ?? null
))
const hasPerson = computed(() => Boolean(selectedSavedPerson.value || temporaryPersonFile.value))
const selectedReferenceTypes = computed(() => (
  TRYON_REFERENCE_TYPES.filter((referenceType) => Boolean(references.value[referenceType]))
))
const unresolvedDuplicateTypes = computed(() => TRYON_REFERENCE_TYPES.filter((referenceType) => (
  (draftCandidates.value[referenceType]?.length ?? 0) > 1
  && !references.value[referenceType]
)))
const hasModeConflict = computed(() => Boolean(
  references.value.overall
  && (references.value.upper || references.value.lower),
))
const selectedReferencesAreSupported = computed(() => selectedReferenceTypes.value.every(
  (referenceType) => capabilities.value?.supported_reference_types.includes(referenceType),
))
const supportedFavoriteItems = computed(() => favoriteItems.value.filter(
  (row) => referenceTypeForCatalogItem(row.item) !== null,
))
const canSubmit = computed(() => Boolean(
  capabilities.value?.available
  && hasPerson.value
  && selectedReferenceTypes.value.length > 0
  && !unresolvedDuplicateTypes.value.length
  && !hasModeConflict.value
  && selectedReferencesAreSupported.value
  && !submitting.value
  && !['queued', 'running'].includes(job.value?.status ?? ''),
))
const submitHint = computed(() => {
  if (capabilityLoading.value) return '正在檢查試穿服務…'
  if (!capabilities.value?.available) return capabilities.value?.reason || '試穿服務目前無法使用。'
  if (!hasPerson.value) return '請先選擇或上傳一張人物照。'
  if (!selectedReferenceTypes.value.length) return '請至少選擇一件可試穿的服飾。'
  if (unresolvedDuplicateTypes.value.length) return '同一槽位有多件候選商品，請先選定一件。'
  if (hasModeConflict.value) return '請先選擇連身或上下身模式。'
  if (!selectedReferencesAreSupported.value) return '目前服務不支援其中一個服飾槽位。'
  if (job.value?.status === 'queued' || job.value?.status === 'running') return '目前已有一個試穿工作正在處理。'
  return `人物與 ${selectedReferenceTypes.value.length} 個服飾槽位已就緒。`
})
const statusLabel = computed(() => {
  if (!job.value) return ''
  return {
    queued: '等待處理',
    running: '正在產生試穿結果',
    succeeded: '試穿完成',
    failed: '試穿失敗',
  }[job.value.status]
})
const canGenerate3D = computed(() => canGenerateHuman3D(
  job.value,
  human3DCapabilities.value,
  human3DJob.value,
) && !human3DSubmitting.value)
const human3DStatus = computed(() => human3DStatusLabel(human3DJob.value))
const human3DIsPending = computed(() => (
  human3DSubmitting.value
  || human3DJob.value?.status === 'queued'
  || human3DJob.value?.status === 'running'
))

function stopPolling() {
  if (pollTimer !== undefined) window.clearTimeout(pollTimer)
  pollTimer = undefined
}

function stopHuman3DPolling() {
  if (human3DPollTimer !== undefined) window.clearTimeout(human3DPollTimer)
  human3DPollTimer = undefined
}

function resetHuman3D() {
  stopHuman3DPolling()
  human3DJob.value = null
  human3DSubmitting.value = false
  resultMode.value = '2d'
}

function isTryOnJob(value: unknown): value is TryOnJob {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === 'string'
    && JOB_STATUSES.includes(candidate.status as TryOnJob['status'])
    && Array.isArray(candidate.reference_types)
    && candidate.reference_types.length > 0
    && candidate.reference_types.every((type) => TRYON_REFERENCE_TYPES.includes(type as TryOnReferenceType))
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
    showError('瀏覽器無法保存最近試穿紀錄。')
  }
}

function discardStoredHistory() {
  try {
    window.localStorage.removeItem(historyStorageKey.value)
  } catch {
    // The in-memory history still works when browser storage is unavailable.
  }
}

function selectHistoryJob(historyJob: TryOnJob) {
  if (job.value?.id !== historyJob.id) resetHuman3D()
  job.value = historyJob
  persistHistory()
}

function replaceHistory(nextJob: TryOnJob, select = false) {
  if (select && job.value?.id !== nextJob.id) resetHuman3D()
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
  job.value = null
  resetHuman3D()
  discardStoredHistory()
}

function referenceTypesLabel(types: TryOnReferenceType[]) {
  return types.map((type) => TRYON_REFERENCE_LABELS[type]).join('、')
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

function syncPersonPreviewUrls() {
  const current = personPreviewUrls.value
  const next: Record<string, string> = {}
  personLibrary.photos.value.forEach((photo) => {
    next[photo.id] = current[photo.id] ?? URL.createObjectURL(photo.blob)
  })
  Object.entries(current).forEach(([id, url]) => {
    if (!next[id]) URL.revokeObjectURL(url)
  })
  personPreviewUrls.value = next
}

function selectPerson(photo: SavedPersonPhoto) {
  selectedPersonId.value = photo.id
  temporaryPersonPreview.value = replacePreview(temporaryPersonPreview.value, null)
  temporaryPersonFile.value = null
  photoError.value = ''
}

async function choosePersonImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  if (!file) return
  photoSaving.value = true
  photoError.value = ''
  const maxBytes = capabilities.value?.max_upload_bytes ?? DEFAULT_MAX_BYTES
  const maxPixels = capabilities.value?.max_image_pixels ?? DEFAULT_MAX_PIXELS
  try {
    await validatePersonPhoto(file, maxBytes, maxPixels)
    try {
      const saved = await personLibrary.add(file, newPhotoName.value, maxBytes, maxPixels)
      syncPersonPreviewUrls()
      selectPerson(saved)
      newPhotoName.value = ''
    } catch {
      temporaryPersonPreview.value = replacePreview(temporaryPersonPreview.value, file)
      temporaryPersonFile.value = file
      selectedPersonId.value = null
      photoError.value = personLibrary.error.value
    }
  } catch (reason) {
    photoError.value = reason instanceof Error ? reason.message : '無法讀取人物照片'
  } finally {
    photoSaving.value = false
  }
}

function removeTemporaryPerson() {
  temporaryPersonPreview.value = replacePreview(temporaryPersonPreview.value, null)
  temporaryPersonFile.value = null
  selectedPersonId.value = personLibrary.defaultPhoto.value?.id ?? null
}

function beginRename(photo: SavedPersonPhoto) {
  editingPhotoId.value = photo.id
  editingPhotoName.value = photo.name
}

async function savePhotoName(photo: SavedPersonPhoto) {
  try {
    await personLibrary.rename(photo.id, editingPhotoName.value)
    editingPhotoId.value = null
    photoError.value = ''
  } catch (reason) {
    photoError.value = reason instanceof Error ? reason.message : '無法更新人物照名稱'
  }
}

async function makeDefault(photo: SavedPersonPhoto) {
  try {
    await personLibrary.setDefault(photo.id)
    syncPersonPreviewUrls()
    photoError.value = ''
  } catch (reason) {
    photoError.value = reason instanceof Error ? reason.message : '無法設定預設人物照'
  }
}

async function deletePersonPhoto(photo: SavedPersonPhoto) {
  if (!window.confirm(`刪除人物照「${photo.name}」？`)) return
  try {
    await personLibrary.remove(photo.id)
    syncPersonPreviewUrls()
    if (selectedPersonId.value === photo.id) {
      selectedPersonId.value = personLibrary.defaultPhoto.value?.id ?? null
    }
    photoError.value = ''
  } catch (reason) {
    photoError.value = reason instanceof Error ? reason.message : '無法刪除人物照'
  }
}

function referencePreview(referenceType: TryOnReferenceType) {
  const selection = references.value[referenceType]
  if (!selection) return ''
  return selection.source === 'favorite' ? selection.item.image_url : selection.previewUrl
}

function referenceName(referenceType: TryOnReferenceType) {
  const selection = references.value[referenceType]
  if (!selection) return ''
  return selection.source === 'favorite' ? selection.item.product_display_name : selection.file.name
}

function removeReference(referenceType: TryOnReferenceType) {
  const current = references.value[referenceType]
  if (current?.source === 'upload') URL.revokeObjectURL(current.previewUrl)
  const next = { ...references.value }
  delete next[referenceType]
  references.value = next
  const nextCandidates = { ...draftCandidates.value }
  delete nextCandidates[referenceType]
  draftCandidates.value = nextCandidates
}

function clearReferences() {
  Object.values(references.value).forEach((selection) => {
    if (selection?.source === 'upload') URL.revokeObjectURL(selection.previewUrl)
  })
  references.value = {}
  draftCandidates.value = {}
  unsupportedItems.value = []
}

function setFavoriteReference(item: CatalogItem) {
  const referenceType = referenceTypeForCatalogItem(item)
  if (!referenceType) return
  const current = references.value[referenceType]
  if (current?.source === 'upload') URL.revokeObjectURL(current.previewUrl)
  references.value = {
    ...references.value,
    [referenceType]: { source: 'favorite', item },
  }
  draftCandidates.value = {
    ...draftCandidates.value,
    [referenceType]: [item],
  }
}

function favoriteItemSelected(item: CatalogItem) {
  const referenceType = referenceTypeForCatalogItem(item)
  if (!referenceType) return false
  const selection = references.value[referenceType]
  return selection?.source === 'favorite' && selection.item.id === item.id
}

function favoriteReferenceTypeLabel(item: CatalogItem) {
  const referenceType = referenceTypeForCatalogItem(item)
  return referenceType ? TRYON_REFERENCE_LABELS[referenceType] : '目前不支援'
}

function chooseCandidate(referenceType: TryOnReferenceType, item: CatalogItem) {
  references.value = {
    ...references.value,
    [referenceType]: { source: 'favorite', item },
  }
}

function chooseReferenceImage(event: Event, referenceType: TryOnReferenceType) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  if (!file) return
  const current = references.value[referenceType]
  if (current?.source === 'upload') URL.revokeObjectURL(current.previewUrl)
  references.value = {
    ...references.value,
    [referenceType]: {
      source: 'upload',
      file,
      previewUrl: URL.createObjectURL(file),
    },
  }
  draftCandidates.value = { ...draftCandidates.value, [referenceType]: [] }
}

function chooseClothingMode(mode: 'overall' | 'separates') {
  if (mode === 'overall') {
    removeReference('upper')
    removeReference('lower')
  } else {
    removeReference('overall')
  }
}

function handleWardrobeTabKeydown(event: KeyboardEvent, currentTab: WardrobeTab) {
  let nextIndex: number | null = null
  const currentIndex = WARDROBE_TABS.indexOf(currentTab)
  if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
    nextIndex = (currentIndex - 1 + WARDROBE_TABS.length) % WARDROBE_TABS.length
  } else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
    nextIndex = (currentIndex + 1) % WARDROBE_TABS.length
  } else if (event.key === 'Home') {
    nextIndex = 0
  } else if (event.key === 'End') {
    nextIndex = WARDROBE_TABS.length - 1
  }
  if (nextIndex === null) return
  event.preventDefault()
  const nextTab = WARDROBE_TABS[nextIndex]
  wardrobeTab.value = nextTab
  const tablist = (event.currentTarget as HTMLElement).closest('[role="tablist"]')
  window.requestAnimationFrame(() => {
    tablist?.querySelector<HTMLButtonElement>(`#tryon-source-tab-${nextTab}`)?.focus()
  })
}

function applyDraft(draft: TryOnDraft) {
  if (draft.source === 'favorite-outfit') clearReferences()
  unsupportedItems.value = [...draft.unsupportedItems]
  draftCandidates.value = draft.source === 'favorite-outfit'
    ? { ...draft.candidates }
    : { ...draftCandidates.value, ...draft.candidates }
  TRYON_REFERENCE_TYPES.forEach((referenceType) => {
    const candidates = draft.candidates[referenceType] ?? []
    if (candidates.length === 1) setFavoriteReference(candidates[0])
    if (candidates.length > 1) {
      const current = references.value[referenceType]
      if (current?.source === 'upload') URL.revokeObjectURL(current.previewUrl)
      const next = { ...references.value }
      delete next[referenceType]
      references.value = next
      draftCandidates.value = { ...draftCandidates.value, [referenceType]: candidates }
    }
  })
  wardrobeTab.value = draft.source === 'favorite-outfit' ? 'outfits' : 'items'
}

function selectFavoriteOutfit(outfit: { id: number; items: CatalogItem[] }) {
  applyDraft(createTryOnDraft(outfit.items, 'favorite-outfit', outfit.id))
}

function outfitSelected(outfit: { items: CatalogItem[] }) {
  const selectedIds = new Set(Object.values(references.value)
    .filter((selection): selection is Extract<TryOnReferenceSelection, { source: 'favorite' }> => selection?.source === 'favorite')
    .map((selection) => selection.item.id))
  const supportedIds = outfit.items
    .filter((item) => referenceTypeForCatalogItem(item))
    .map((item) => item.id)
  return supportedIds.length > 0 && supportedIds.every((id) => selectedIds.has(id))
}

function isReferenceDisabled(referenceType: TryOnReferenceType) {
  return Boolean(
    capabilities.value
    && !capabilities.value.supported_reference_types.includes(referenceType),
  )
}

async function loadCapabilities() {
  capabilityLoading.value = true
  try {
    capabilities.value = await getTryOnCapabilities()
    if (!capabilities.value.available) {
      showError(`試穿服務尚未連線：${capabilities.value.reason || '請稍後再試'}`)
    }
  } catch (reason) {
    capabilities.value = null
    showError(reason instanceof Error ? reason.message : '無法檢查試穿服務狀態')
  } finally {
    capabilityLoading.value = false
  }
}

async function loadHuman3DCapabilities() {
  human3DCapabilityLoading.value = true
  try {
    human3DCapabilities.value = await getHuman3DCapabilities()
  } catch (reason) {
    human3DCapabilities.value = {
      available: false,
      reason: reason instanceof Error ? reason.message : '無法檢查 3D 服務狀態',
      artifact_formats: ['ply'],
    }
  } finally {
    human3DCapabilityLoading.value = false
  }
}

async function reloadCapabilities() {
  await Promise.allSettled([loadCapabilities(), loadHuman3DCapabilities()])
}

async function pollHuman3DJob() {
  stopHuman3DPolling()
  const current = human3DJob.value
  if (!current || !componentActive) return
  try {
    const updated = await getHuman3DJob(current.id)
    if (human3DJob.value?.id !== current.id || job.value?.id !== current.try_on_job_id) return
    human3DJob.value = updated
    if (human3DJob.value.status === 'succeeded') {
      resultMode.value = '3d'
      return
    }
    if (human3DJob.value.status === 'failed') return
    human3DPollTimer = window.setTimeout(pollHuman3DJob, 2000)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '無法更新 3D 工作狀態')
    human3DPollTimer = window.setTimeout(pollHuman3DJob, 5000)
  }
}

async function generateHuman3D() {
  if (!job.value || !canGenerate3D.value) return
  const tryOnJobId = job.value.id
  stopHuman3DPolling()
  human3DSubmitting.value = true
  try {
    const created = await createHuman3DJob(tryOnJobId, props.userKey)
    if (job.value?.id !== tryOnJobId) return
    human3DJob.value = created
    human3DPollTimer = window.setTimeout(pollHuman3DJob, 1200)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '無法建立 3D 工作')
    await loadHuman3DCapabilities()
  } finally {
    human3DSubmitting.value = false
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
  if (failedRequests) {
    showError(`有 ${failedRequests} 筆紀錄暫時無法更新，將自動重試。`)
  }
  const hasPendingJobs = historyJobs.value.some(
    (historyJob) => historyJob.status === 'queued' || historyJob.status === 'running',
  )
  if (hasPendingJobs || failedRequests) {
    pollTimer = window.setTimeout(synchronizeHistory, failedRequests ? 5000 : 2000)
  }
}

function extensionForType(contentType: string) {
  if (contentType === 'image/png') return 'png'
  if (contentType === 'image/webp') return 'webp'
  return 'jpg'
}

async function catalogItemFile(item: CatalogItem, referenceType: TryOnReferenceType): Promise<File> {
  const response = await fetch(item.image_url)
  if (!response.ok) throw new Error(`${TRYON_REFERENCE_LABELS[referenceType]}商品圖片讀取失敗，請重新選擇`)
  const blob = await response.blob()
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(blob.type)) {
    throw new Error(`${TRYON_REFERENCE_LABELS[referenceType]}商品圖片格式不支援`)
  }
  return new File(
    [blob],
    `favorite-${item.id}.${extensionForType(blob.type)}`,
    { type: blob.type },
  )
}

async function materializeReferences() {
  const entries = await Promise.all(selectedReferenceTypes.value.map(async (referenceType) => {
    const selection = references.value[referenceType]
    if (!selection) throw new Error(`請重新選擇${TRYON_REFERENCE_LABELS[referenceType]}`)
    const file = selection.source === 'upload'
      ? selection.file
      : await catalogItemFile(selection.item, referenceType)
    return [referenceType, file] as const
  }))
  return Object.fromEntries(entries) as Partial<Record<TryOnReferenceType, File>>
}

function selectedPersonFile(): File | null {
  if (temporaryPersonFile.value) return temporaryPersonFile.value
  const saved = selectedSavedPerson.value
  if (!saved) return null
  return new File(
    [saved.blob],
    `person-${saved.id}.${extensionForType(saved.mimeType)}`,
    { type: saved.mimeType },
  )
}

async function submit() {
  const person = selectedPersonFile()
  if (!canSubmit.value || !person) return
  stopPolling()
  submitting.value = true
  try {
    const referenceFiles = await materializeReferences()
    const createdJob = await createTryOnJob(person, referenceFiles, props.userKey)
    replaceHistory(createdJob, true)
    pollTimer = window.setTimeout(synchronizeHistory, 2000)
  } catch (reason) {
    const submitError = reason instanceof Error ? reason.message : '無法建立試穿工作'
    await loadCapabilities()
    showError(submitError)
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

watch(() => props.draft?.revision, () => {
  if (props.draft) applyDraft(props.draft)
}, { immediate: true })

watch(personLibrary.photos, () => {
  syncPersonPreviewUrls()
  if (!selectedPersonId.value && !temporaryPersonFile.value) {
    selectedPersonId.value = personLibrary.defaultPhoto.value?.id ?? null
  }
}, { deep: true })

onMounted(async () => {
  componentActive = true
  loadHistory()
  await Promise.allSettled([
    loadCapabilities(),
    loadHuman3DCapabilities(),
    personLibrary.load(),
    loadFavorites(),
  ])
  syncPersonPreviewUrls()
  if (!selectedPersonId.value) selectedPersonId.value = personLibrary.defaultPhoto.value?.id ?? null
  void synchronizeHistory(true)
  cleanupTimer = window.setInterval(cleanExpiredHistory, 60_000)
})

onBeforeUnmount(() => {
  componentActive = false
  stopPolling()
  stopHuman3DPolling()
  if (cleanupTimer !== undefined) window.clearInterval(cleanupTimer)
  temporaryPersonPreview.value = replacePreview(temporaryPersonPreview.value, null)
  Object.values(personPreviewUrls.value).forEach((preview) => URL.revokeObjectURL(preview))
  Object.values(references.value).forEach((selection) => {
    if (selection?.source === 'upload') URL.revokeObjectURL(selection.previewUrl)
  })
})
</script>

<template>
  <section class="page-view tryon-view">
    <header class="view-heading">
      <div>
        <span class="section-kicker">Virtual try-on</span>
        <h2>虛擬試穿</h2>
        <p>選擇人物與穿搭後，即可直接生成試穿結果。</p>
      </div>
      <button class="secondary-button" :disabled="capabilityLoading || human3DCapabilityLoading" @click="reloadCapabilities">
        <RefreshCw :size="16" :class="{ spinning: capabilityLoading || human3DCapabilityLoading }" />重新檢查服務
      </button>
    </header>

    <div class="tryon-layout">
      <section class="tryon-form-card">
        <section class="tryon-workspace-section" aria-labelledby="tryon-person-heading">
          <header class="tryon-panel-heading">
            <div><span>Person profile</span><h3 id="tryon-person-heading">人物設定</h3></div>
          </header>

          <p v-if="personLibrary.error.value || photoError" class="tryon-inline-error" role="alert">
            {{ photoError || personLibrary.error.value }}
          </p>
          <div v-if="personLibrary.loading.value" class="loading-state">正在載入人物照…</div>
          <div v-else-if="personLibrary.photos.value.length" class="person-photo-grid">
            <article
              v-for="photo in personLibrary.photos.value"
              :key="photo.id"
              class="person-photo-card"
              :class="{ selected: selectedPersonId === photo.id }"
            >
              <button type="button" class="person-photo-select" @click="selectPerson(photo)">
                <img :src="personPreviewUrls[photo.id]" :alt="photo.name" />
                <span v-if="selectedPersonId === photo.id" class="selection-badge"><Check :size="13" />已選取</span>
                <span v-if="photo.isDefault" class="default-badge"><Star :size="12" fill="currentColor" />預設</span>
              </button>
              <div class="person-photo-meta">
                <template v-if="editingPhotoId === photo.id">
                  <div class="person-photo-rename">
                    <input
                      :id="`person-name-${photo.id}`"
                      v-model="editingPhotoName"
                      maxlength="40"
                      @keyup.enter="savePhotoName(photo)"
                    />
                    <button type="button" aria-label="儲存名稱" @click="savePhotoName(photo)"><Check :size="14" /></button>
                    <button type="button" aria-label="取消重新命名" @click="editingPhotoId = null"><X :size="14" /></button>
                  </div>
                </template>
                <template v-else>
                  <strong>{{ photo.name }}</strong>
                  <small>{{ photo.width }} × {{ photo.height }}</small>
                </template>
              </div>
              <div class="person-photo-actions">
                <button v-if="!photo.isDefault" type="button" @click="makeDefault(photo)"><Star :size="13" />設為預設</button>
                <button type="button" @click="beginRename(photo)"><Pencil :size="13" />命名</button>
                <button type="button" class="danger" @click="deletePersonPhoto(photo)"><Trash2 :size="13" />刪除</button>
              </div>
            </article>
          </div>

          <article v-if="temporaryPersonFile" class="temporary-person-card">
            <img :src="temporaryPersonPreview" alt="本次人物照預覽" />
            <div><strong>本次人物照</strong><small>未保存，離開或重新載入後會消失。</small></div>
            <button type="button" class="tryon-remove-button" @click="removeTemporaryPerson"><Trash2 :size="13" />移除</button>
          </article>

          <div class="person-photo-upload" :class="{ disabled: !personLibrary.canAdd.value }">
            <div><ImagePlus :size="25" /><strong>新增人物照</strong><small>建議使用正面全身照</small></div>
            <label class="secondary-button person-upload-button" :aria-disabled="!personLibrary.canAdd.value || photoSaving">
              <LoaderCircle v-if="photoSaving" :size="16" class="spinning" />
              <Upload v-else :size="16" />
              {{ personLibrary.canAdd.value ? '選擇並保存照片' : '人物照已達上限' }}
              <input
                class="tryon-file-input"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                :disabled="!personLibrary.canAdd.value || photoSaving"
                aria-label="選擇並保存人物照片"
                @change="choosePersonImage"
              />
            </label>
          </div>

        </section>

        <section class="tryon-workspace-section" aria-labelledby="tryon-clothes-heading">
          <header class="tryon-panel-heading">
            <div><span>Outfit selection</span><h3 id="tryon-clothes-heading">選擇穿搭</h3></div>
            <button v-if="selectedReferenceTypes.length" type="button" class="text-button danger" @click="clearReferences">
              <Trash2 :size="14" />清空穿搭
            </button>
          </header>

          <div class="tryon-slot-grid">
            <article
              v-for="referenceType in TRYON_REFERENCE_TYPES"
              :key="referenceType"
              class="tryon-slot-card"
              :class="{ selected: references[referenceType], unresolved: (draftCandidates[referenceType]?.length ?? 0) > 1 && !references[referenceType] }"
            >
              <header>
                <strong>{{ TRYON_REFERENCE_LABELS[referenceType] }}</strong>
                <span v-if="references[referenceType]" class="tryon-slot-status"><Check :size="13" />已選取</span>
              </header>
              <div v-if="references[referenceType]" class="tryon-slot-preview">
                <img :src="referencePreview(referenceType)" :alt="referenceName(referenceType)" />
                <span>{{ referenceName(referenceType) }}</span>
                <button type="button" :aria-label="`移除${TRYON_REFERENCE_LABELS[referenceType]}`" @click="removeReference(referenceType)"><X :size="15" /></button>
              </div>
              <div v-else-if="(draftCandidates[referenceType]?.length ?? 0) > 1" class="tryon-candidate-list">
                <small>請選擇一件</small>
                <button
                  v-for="candidate in draftCandidates[referenceType]"
                  :key="candidate.id"
                  type="button"
                  @click="chooseCandidate(referenceType, candidate)"
                >
                  <img :src="candidate.image_url" :alt="candidate.product_display_name" />
                  <span>{{ candidate.product_display_name }}</span>
                </button>
              </div>
              <label v-else-if="wardrobeTab === 'upload'" class="tryon-slot-empty upload">
                <Upload :size="20" /><span>上傳{{ TRYON_REFERENCE_LABELS[referenceType] }}</span>
                <input
                  class="tryon-file-input"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  :disabled="isReferenceDisabled(referenceType)"
                  :aria-label="`上傳${TRYON_REFERENCE_LABELS[referenceType]}圖片`"
                  @change="chooseReferenceImage($event, referenceType)"
                />
              </label>
              <div v-else class="tryon-slot-empty"><Shirt :size="20" /><span>尚未選擇</span></div>
            </article>
          </div>

          <div v-if="hasModeConflict" class="tryon-conflict" role="alert">
            <AlertCircle :size="18" />
            <div><strong>請選擇一種穿搭模式</strong><p>連身服飾不能與上身或下身同時送入模型。</p></div>
            <div class="tryon-conflict-actions">
              <button type="button" @click="chooseClothingMode('overall')">保留連身</button>
              <button type="button" @click="chooseClothingMode('separates')">保留上下身</button>
            </div>
          </div>

          <div v-if="unsupportedItems.length" class="tryon-unsupported" role="status">
            <AlertCircle :size="17" />
            <div><strong>以下品項目前不支援試穿</strong><p>{{ unsupportedItems.map((item) => item.product_display_name).join('、') }}</p></div>
          </div>

          <div class="tryon-source-tabs" role="tablist" aria-label="穿搭來源">
            <button
              id="tryon-source-tab-outfits"
              type="button"
              role="tab"
              :tabindex="wardrobeTab === 'outfits' ? 0 : -1"
              :aria-selected="wardrobeTab === 'outfits'"
              aria-controls="tryon-source-panel-outfits"
              :class="{ active: wardrobeTab === 'outfits' }"
              @click="wardrobeTab = 'outfits'"
              @keydown="handleWardrobeTabKeydown($event, 'outfits')"
            >
              <Images :size="16" />收藏整套
            </button>
            <button
              id="tryon-source-tab-items"
              type="button"
              role="tab"
              :tabindex="wardrobeTab === 'items' ? 0 : -1"
              :aria-selected="wardrobeTab === 'items'"
              aria-controls="tryon-source-panel-items"
              :class="{ active: wardrobeTab === 'items' }"
              @click="wardrobeTab = 'items'"
              @keydown="handleWardrobeTabKeydown($event, 'items')"
            >
              <Shirt :size="16" />收藏單品
            </button>
            <button
              id="tryon-source-tab-upload"
              type="button"
              role="tab"
              :tabindex="wardrobeTab === 'upload' ? 0 : -1"
              :aria-selected="wardrobeTab === 'upload'"
              aria-controls="tryon-source-panel-upload"
              :class="{ active: wardrobeTab === 'upload' }"
              @click="wardrobeTab = 'upload'"
              @keydown="handleWardrobeTabKeydown($event, 'upload')"
            >
              <Upload :size="16" />自行上傳
            </button>
          </div>

          <div
            :id="`tryon-source-panel-${wardrobeTab}`"
            role="tabpanel"
            :aria-labelledby="`tryon-source-tab-${wardrobeTab}`"
          >
            <div v-if="favoritesLoading" class="loading-state">正在載入收藏…</div>
            <div v-else-if="wardrobeTab === 'outfits'" class="tryon-wardrobe-grid outfits">
              <button
                v-for="outfit in favoriteOutfits"
                :key="outfit.id"
                type="button"
                class="tryon-wardrobe-outfit"
                :class="{ selected: outfitSelected(outfit) }"
                @click="selectFavoriteOutfit(outfit)"
              >
                <span class="tryon-wardrobe-images">
                  <img v-for="item in outfit.items" :key="item.id" :src="item.image_url" :alt="item.product_display_name" />
                </span>
                <span>
                  <strong>收藏穿搭</strong>
                  <small>{{ outfit.items.length }} 件商品{{ outfitSelected(outfit) ? ' · 已選取' : '' }}</small>
                </span>
                <Check v-if="outfitSelected(outfit)" :size="17" />
              </button>
              <div v-if="!favoriteOutfits.length" class="tryon-empty-source"><Images :size="27" /><p>還沒有收藏整套穿搭。</p></div>
            </div>
            <div v-else-if="wardrobeTab === 'items'" class="tryon-wardrobe-grid items">
              <button
                v-for="row in supportedFavoriteItems"
                :key="row.item.id"
                type="button"
                class="tryon-wardrobe-item"
                :class="{ selected: favoriteItemSelected(row.item) }"
                @click="setFavoriteReference(row.item)"
              >
                <img :src="row.item.image_url" :alt="row.item.product_display_name" />
                <span>
                  <strong>{{ row.item.product_display_name }}</strong>
                  <small>{{ favoriteReferenceTypeLabel(row.item) }}{{ favoriteItemSelected(row.item) ? ' · 已選取' : '' }}</small>
                </span>
                <Check v-if="favoriteItemSelected(row.item)" :size="16" />
              </button>
              <div v-if="!supportedFavoriteItems.length" class="tryon-empty-source"><Shirt :size="27" /><p>還沒有可試穿的收藏單品。</p></div>
            </div>
            <div v-else class="tryon-upload-guidance">
              <Upload :size="24" />
              <div><strong>從上方槽位上傳商品照</strong><p>每個槽位只能選一張；連身服飾不能與上身或下身同時使用。</p></div>
            </div>
          </div>

        </section>

        <section class="tryon-submit-panel" aria-labelledby="tryon-submit-heading">
          <div>
            <strong id="tryon-submit-heading">直接生成試穿結果</strong>
            <p aria-live="polite">{{ submitHint }}</p>
          </div>
          <button class="primary-button tryon-submit" :disabled="!canSubmit" @click="submit">
            <LoaderCircle v-if="submitting" :size="17" class="spinning" />
            <ScanFace v-else :size="17" />
            {{ submitting ? '建立工作中…' : '開始虛擬試穿' }}
          </button>
          <p class="tryon-limit">每張圖片上限 {{ Math.round((capabilities?.max_upload_bytes || DEFAULT_MAX_BYTES) / 1048576) }} MiB</p>
        </section>
      </section>

      <section class="tryon-result-card">
        <div v-if="historyJobs.length" class="tryon-history">
          <div class="tryon-history-heading">
            <div><strong>最近試穿</strong></div>
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
        </div>
        <div class="tryon-result-body" aria-live="polite">
          <div v-if="job?.status === 'succeeded' && job.result_url" class="tryon-result">
            <Human3DViewer
              v-if="resultMode === '3d' && human3DJob?.status === 'succeeded' && human3DJob.result_url"
              :src="human3DJob.result_url"
            />
            <img v-else :src="job.result_url" alt="虛擬試穿結果" />
            <div class="tryon-result-status"><CheckCircle2 :size="17" /><strong>{{ resultMode === '3d' ? '3D View 已完成' : statusLabel }}</strong></div>
            <div class="human3d-actions">
              <button
                v-if="resultMode === '3d'"
                type="button"
                class="secondary-button"
                @click="resultMode = '2d'"
              >
                返回 2D 結果
              </button>
              <button
                v-else-if="human3DJob?.status === 'succeeded' && human3DJob.result_url"
                type="button"
                class="primary-button"
                @click="resultMode = '3d'"
              >
                <Box :size="17" />開啟 3D View
              </button>
              <button
                v-else-if="human3DCapabilities?.available"
                type="button"
                class="primary-button"
                :disabled="!canGenerate3D"
                @click="generateHuman3D"
              >
                <LoaderCircle v-if="human3DIsPending" :size="17" class="spinning" />
                <Box v-else :size="17" />
                {{ human3DIsPending ? human3DStatus || '準備建立 3D 模型…' : '產生 3D View' }}
              </button>
              <p v-else-if="!human3DCapabilityLoading" class="human3d-unavailable">
                3D View 目前無法使用。{{ human3DCapabilities?.reason || '' }}
              </p>
            </div>
            <div v-if="human3DJob?.status === 'queued' || human3DJob?.status === 'running'" class="human3d-progress" role="status">
              <LoaderCircle :size="16" class="spinning" />{{ human3DStatus }} 你仍可查看 2D 結果。
            </div>
            <div v-else-if="human3DJob?.status === 'failed'" class="human3d-progress error" role="alert">
              <AlertCircle :size="16" />{{ human3DStatus }}：{{ human3DJob.error || '請重新嘗試。' }}
            </div>
            <p v-if="resultMode === '3d'" class="human3d-caveat">
              3D View 由單張試穿圖片推估，未出現在原圖中的側面與背面細節可能與實際服裝不同。
            </p>
          </div>
          <div v-else class="tryon-result-placeholder" :class="{ processing: job?.status === 'queued' || job?.status === 'running' }">
            <LoaderCircle v-if="job?.status === 'queued' || job?.status === 'running'" :size="36" class="spinning" />
            <ScanFace v-else :size="42" />
            <h3>{{ statusLabel || '試穿結果會顯示在這裡' }}</h3>
            <p v-if="job?.status === 'queued'">正在等待處理。</p>
            <p v-else-if="job?.status === 'running'">正在生成試穿結果。</p>
            <p v-else-if="job?.status === 'failed'">{{ job.error || '這次試穿未能完成，請重新送出。' }}</p>
            <p v-else>選好人物與穿搭並送出後，結果會保留在這裡方便比較。</p>
          </div>
        </div>
      </section>
    </div>
  </section>
</template>
