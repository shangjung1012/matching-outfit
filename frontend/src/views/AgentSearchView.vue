<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef } from 'vue'
import {
  AlertCircle, ArrowLeft, BookOpenText, Check, ChevronDown, ChevronUp,
  MessageSquare, MessageSquarePlus, RotateCcw, Send, Sparkles, Square,
} from 'lucide-vue-next'
import {
  clarifyRequirements,
  createQueryPlan,
  getRecommendations,
  proposeSoftFromOutfit,
  refineQueryPlan,
} from '../api'
import OutfitCard from '../components/OutfitCard.vue'
import PreferenceProposalPanel from '../components/PreferenceProposalPanel.vue'
import QueryReview from '../components/QueryReview.vue'
import { useUserLibrary } from '../composables/useUserLibrary'
import type {
  Audience,
  FashionObservationTrace,
  FashionIntent,
  OutfitRecommendation,
  PipelineDebugSession,
  QueryDraft,
  QueryPlanDebug,
  RecommendationDebug,
  RequirementSummary,
  StylePreferenceProposal,
  StylingGuide,
} from '../types'

const props = defineProps<{ userKey: string }>()
const emit = defineEmits<{
  preferenceUpdated: []
  openKnowledge: []
  debugUpdated: [trace: PipelineDebugSession]
}>()
const {
  favoriteItemIds,
  isPreferred,
  isOutfitFavorited,
  setFavoriteItems,
  setFavoriteOutfit,
  confirmPreferences,
  deactivatePreferenceOrigin,
} = useUserLibrary(props.userKey)

interface ChatMessage {
  id: number
  role: 'agent' | 'user'
  text: string
}

type AgentActivityKind = 'clarifying' | 'planning' | 'refining' | 'searching'

interface AgentRequestError {
  message: string
  retry: () => Promise<void>
}

const activityLabels: Record<AgentActivityKind, string> = {
  clarifying: '正在理解你的需求',
  planning: '正在整理需求並產生搜尋 query',
  refining: '正在依照補充條件調整 query',
  searching: '正在搜尋並評估搭配',
}

const messages = ref<ChatMessage[]>([
  { id: 1, role: 'agent', text: '今天想找什麼樣的穿搭？告訴我場合、風格、顏色或預算。' },
])
const draft = ref('')
const queries = ref<QueryDraft[]>([])
const recommendations = ref<OutfitRecommendation[]>([])
const discardedRecommendations = ref<OutfitRecommendation[]>([])
const showDiscarded = ref(false)
const likedOutfitIds = ref(new Set<string>())
const proposal = ref<StylePreferenceProposal | null>(null)
const preferenceStatus = ref('')
const proposalArea = ref<HTMLElement | null>(null)
const messageList = ref<HTMLElement | null>(null)
const agentActivity = ref<AgentActivityKind | null>(null)
const typingVisible = ref(false)
const actionLoading = ref(false)
const actionError = ref('')
const requestError = shallowRef<AgentRequestError | null>(null)
const stoppedNotice = ref('')
const isNearMessageBottom = ref(true)
const hasUnreadMessage = ref(false)
const stage = ref<'start' | 'review' | 'results'>('start')
const originalRequest = ref('')
const audience = ref<Audience | ''>('')
const requirements = ref<RequirementSummary | null>(null)
const stylingGuide = ref<StylingGuide | null>(null)
const fashionIntent = ref<FashionIntent | null>(null)
const planDebug = ref<QueryPlanDebug | null>(null)
const planningKnowledge = ref<FashionObservationTrace[]>([])
const recommendationDebug = ref<RecommendationDebug | null>(null)
const reviewNote = ref('')
const knowledgeNote = ref('')
const missingFields = ref<string[]>([])
const readyToPlan = ref(false)
let messageId = 2
let typingTimer: ReturnType<typeof setTimeout> | null = null
let activeController: AbortController | null = null
let requestSequence = 0

const selectedCount = computed(() => queries.value.filter((query) => query.selected).length)
const hasUserDetails = computed(() => messages.value.some((message) => message.role === 'user'))
const agentBusy = computed(() => agentActivity.value !== null)
const activityLabel = computed(() => (
  agentActivity.value ? activityLabels[agentActivity.value] : ''
))
const showQuerySkeleton = computed(() => (
  typingVisible.value
  && (agentActivity.value === 'planning' || agentActivity.value === 'refining')
))
const showOutfitSkeleton = computed(() => (
  typingVisible.value && agentActivity.value === 'searching'
))
const composerPlaceholder = computed(() => {
  if (stage.value === 'start') return '回答 Agent 的問題，或補充你的穿搭需求'
  if (stage.value === 'review') return '補充調整，例如：不要裙子、再正式一點'
  return '若要搜尋其他穿搭，請開啟新的對話'
})

type RequirementDisplayField = Exclude<
  keyof RequirementSummary,
  'search_brief' | 'tag_translations' | 'defaulted_fields' | 'weather'
>

const requirementLabels: Record<RequirementDisplayField, string> = {
  location: '地點',
  target_date: '日期（台灣時間）',
  occasions: '場合',
  seasons: '季節',
  times_of_day: '時段',
  climates: '氣候與環境',
  formalities: '正式程度',
  activities: '活動',
  styles: '風格',
  special_requirements: '特殊要求',
  additional_notes: '其他補充',
}

const quickPrompts = [
  '適合上班的簡約藍色穿搭，預算 3000 元',
  '週末休閒穿搭，不要裙子',
  '想找粉色的夏季洋裝',
]

function requirementValue(field: RequirementDisplayField): string {
  const value = requirements.value?.[field]
  if (Array.isArray(value)) {
    return value.length
      ? value.map((tag) => requirements.value?.tag_translations[tag] || tag).join('、')
      : '尚未提供'
  }
  return value?.trim() || '尚未提供'
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function handleMessageScroll() {
  const element = messageList.value
  if (!element) return
  isNearMessageBottom.value = element.scrollHeight - element.scrollTop - element.clientHeight < 64
  if (isNearMessageBottom.value) hasUnreadMessage.value = false
}

function scrollConversation(force = false) {
  void nextTick(() => {
    const element = messageList.value
    if (!element) return
    if (force || isNearMessageBottom.value) {
      element.scrollTo({
        top: element.scrollHeight,
        behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      })
      isNearMessageBottom.value = true
      hasUnreadMessage.value = false
    } else {
      hasUnreadMessage.value = true
    }
  })
}

function addMessage(role: 'agent' | 'user', text: string, forceScroll = false) {
  messages.value.push({ id: messageId++, role, text })
  scrollConversation(forceScroll)
}

function publishDebug() {
  emit('debugUpdated', {
    updated_at: new Date().toISOString(),
    messages: messages.value.map(({ role, text }) => ({ role, text })),
    original_input: originalRequest.value,
    requirements: requirements.value,
    fashion_intent: fashionIntent.value,
    queries: queries.value,
    styling_guide: stylingGuide.value,
    plan_debug: planDebug.value,
    recommendation_debug: recommendationDebug.value,
    recommendations: recommendations.value,
    discarded_recommendations: discardedRecommendations.value,
    review_note: reviewNote.value,
    knowledge_note: knowledgeNote.value,
  })
}

function clearTypingTimer() {
  if (typingTimer !== null) {
    clearTimeout(typingTimer)
    typingTimer = null
  }
}

function isAbortError(reason: unknown): boolean {
  return reason instanceof Error && reason.name === 'AbortError'
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : '發生未知錯誤，請稍後再試。'
}

function cancelAgentRequest(showNotice: boolean) {
  requestSequence += 1
  activeController?.abort()
  activeController = null
  clearTypingTimer()
  agentActivity.value = null
  typingVisible.value = false
  requestError.value = null
  if (showNotice) {
    stoppedNotice.value = '已停止目前操作。你的草稿仍保留，可以修改後再送出。'
    scrollConversation()
  }
}

function stopAgentRequest() {
  if (agentBusy.value) cancelAgentRequest(true)
}

async function runAgentRequest<T>(
  kind: AgentActivityKind,
  request: (signal: AbortSignal) => Promise<T>,
  onSuccess: (response: T) => void,
  retry: () => Promise<void>,
) {
  if (agentBusy.value) return
  const sequence = ++requestSequence
  const controller = new AbortController()
  activeController = controller
  agentActivity.value = kind
  requestError.value = null
  stoppedNotice.value = ''
  actionError.value = ''
  typingVisible.value = false
  clearTypingTimer()
  typingTimer = setTimeout(() => {
    if (sequence !== requestSequence) return
    typingVisible.value = true
    scrollConversation()
  }, 250)

  try {
    const response = await request(controller.signal)
    if (sequence !== requestSequence) return
    onSuccess(response)
  } catch (reason) {
    if (sequence !== requestSequence || isAbortError(reason)) return
    requestError.value = { message: errorMessage(reason), retry }
    scrollConversation()
  } finally {
    if (sequence === requestSequence) {
      clearTypingTimer()
      activeController = null
      agentActivity.value = null
      typingVisible.value = false
    }
  }
}

async function retryAgentRequest() {
  const retry = requestError.value?.retry
  if (retry && !agentBusy.value) await retry()
}

async function runAction(task: () => Promise<void>) {
  if (actionLoading.value) return
  actionLoading.value = true
  actionError.value = ''
  try {
    await task()
  } catch (reason) {
    actionError.value = errorMessage(reason)
  } finally {
    actionLoading.value = false
  }
}

async function requestClarification(
  chatMessages: Array<{ role: 'agent' | 'user'; text: string }>,
  previousRequirements: RequirementSummary | null,
  selectedAudience: Audience | undefined,
) {
  const retry = () => requestClarification(chatMessages, previousRequirements, selectedAudience)
  await runAgentRequest(
    'clarifying',
    (signal) => clarifyRequirements(
      chatMessages,
      props.userKey,
      previousRequirements,
      selectedAudience,
      signal,
    ),
    (response) => {
      requirements.value = response.requirements
      missingFields.value = response.missing_fields
      readyToPlan.value = response.ready_to_plan
      addMessage('agent', response.reply)
      publishDebug()
    },
    retry,
  )
}

async function requestRefinement(
  text: string,
  existingQueries: QueryDraft[],
  previousRequest: string,
  currentRequirements: RequirementSummary | null,
  currentFashionIntent: FashionIntent | null,
  selectedAudience: Audience | undefined,
) {
  const retry = () => requestRefinement(
    text,
    existingQueries,
    previousRequest,
    currentRequirements,
    currentFashionIntent,
    selectedAudience,
  )
  await runAgentRequest(
    'refining',
    (signal) => refineQueryPlan(
      text,
      props.userKey,
      existingQueries,
      previousRequest,
      currentRequirements,
      currentFashionIntent,
      selectedAudience,
      signal,
    ),
    (response) => {
      queries.value = response.queries
      stylingGuide.value = response.styling_guide
      fashionIntent.value = response.fashion_intent
      planDebug.value = response.debug
      requirements.value = response.debug?.requirement_summary ?? requirements.value
      planningKnowledge.value = response.knowledge_observations ?? []
      recommendationDebug.value = null
      audience.value = response.audience ?? audience.value
      originalRequest.value = `${previousRequest} ${text}`.trim()
      addMessage('agent', `已依照補充條件重新規劃 ${response.queries.length} 個搜尋條件。`)
      publishDebug()
    },
    retry,
  )
}

async function requestPlanning(
  planningInput: string,
  currentRequirements: RequirementSummary | null,
  selectedAudience: Audience | undefined,
) {
  const retry = () => requestPlanning(planningInput, currentRequirements, selectedAudience)
  await runAgentRequest(
    'planning',
    (signal) => createQueryPlan(
      planningInput,
      props.userKey,
      currentRequirements,
      selectedAudience,
      signal,
    ),
    (response) => {
      originalRequest.value = planningInput
      queries.value = response.queries
      stylingGuide.value = response.styling_guide
      fashionIntent.value = response.fashion_intent
      planDebug.value = response.debug
      requirements.value = response.debug?.requirement_summary ?? requirements.value
      planningKnowledge.value = response.knowledge_observations ?? []
      recommendationDebug.value = null
      audience.value = response.audience ?? audience.value
      recommendations.value = []
      discardedRecommendations.value = []
      showDiscarded.value = false
      stage.value = 'review'
      addMessage(
        'agent',
        `需求已確認，已產生 ${response.queries.length} 個搜尋條件。${response.planning_note}`,
      )
      publishDebug()
    },
    retry,
  )
}

async function requestRecommendations(
  selectedQueries: QueryDraft[],
  userInput: string,
  currentRequirements: RequirementSummary | null,
  currentStylingGuide: StylingGuide | null,
  selectedAudience: Audience | undefined,
) {
  const retry = () => requestRecommendations(
    selectedQueries,
    userInput,
    currentRequirements,
    currentStylingGuide,
    selectedAudience,
  )
  await runAgentRequest(
    'searching',
    (signal) => getRecommendations(
      selectedQueries,
      props.userKey,
      userInput,
      currentRequirements,
      currentStylingGuide,
      selectedAudience,
      signal,
      fashionIntent.value,
    ),
    (response) => {
      recommendations.value = response.recommendations
      discardedRecommendations.value = response.discarded_recommendations
      recommendationDebug.value = response.debug
      reviewNote.value = response.review_note
      knowledgeNote.value = response.knowledge_note
      showDiscarded.value = false
      likedOutfitIds.value = new Set()
      proposal.value = null
      preferenceStatus.value = ''
      stage.value = 'results'
      addMessage(
        'agent',
        `找到 ${response.recommendations.length} 組搭配，使用 ${response.knowledge_observation_count} 條文章知識。${response.review_note}`,
      )
      publishDebug()
    },
    retry,
  )
}

async function sendRequest(text = draft.value) {
  const content = text.trim()
  if (!content || agentBusy.value || stage.value === 'results') return
  draft.value = ''
  addMessage('user', content, true)
  if (stage.value === 'review') {
    await requestRefinement(
      content,
      queries.value.map((query) => ({ ...query })),
      originalRequest.value,
      requirements.value,
      fashionIntent.value,
      audience.value || undefined,
    )
    return
  }
  await requestClarification(
    messages.value.map(({ role, text: messageText }) => ({ role, text: messageText })),
    requirements.value,
    audience.value || undefined,
  )
}

async function confirmRequirements() {
  if (!hasUserDetails.value || agentBusy.value) return
  const rawUserRequest = messages.value
    .filter((message) => message.role === 'user')
    .map((message) => message.text)
    .join('；')
    .trim()
  const planningInput = rawUserRequest || requirements.value?.search_brief.trim() || ''
  await requestPlanning(
    planningInput,
    requirements.value,
    audience.value || undefined,
  )
}

function startNewConversation() {
  cancelAgentRequest(false)
  messages.value = [
    { id: messageId++, role: 'agent', text: '今天想找什麼樣的穿搭？我會先和你確認場合、時間與其他重要需求。' },
  ]
  draft.value = ''
  queries.value = []
  recommendations.value = []
  discardedRecommendations.value = []
  showDiscarded.value = false
  requirements.value = null
  stylingGuide.value = null
  fashionIntent.value = null
  planDebug.value = null
  planningKnowledge.value = []
  recommendationDebug.value = null
  reviewNote.value = ''
  knowledgeNote.value = ''
  missingFields.value = []
  readyToPlan.value = false
  originalRequest.value = ''
  likedOutfitIds.value = new Set()
  proposal.value = null
  preferenceStatus.value = ''
  actionError.value = ''
  stoppedNotice.value = ''
  hasUnreadMessage.value = false
  isNearMessageBottom.value = true
  stage.value = 'start'
  scrollConversation(true)
}

async function searchOutfits() {
  if (agentBusy.value) return
  await requestRecommendations(
    queries.value.map((query) => ({ ...query })),
    originalRequest.value,
    requirements.value,
    stylingGuide.value,
    audience.value || undefined,
  )
}

function setSelected(id: string, selected: boolean) {
  const query = queries.value.find((item) => item.id === id)
  if (query) query.selected = selected
  publishDebug()
}

function updateQueryText(id: string, text: string) {
  const query = queries.value.find((item) => item.id === id)
  if (query) query.text = text
  publishDebug()
}

function outfitItemIds(outfit: OutfitRecommendation): number[] {
  return outfit.items.map((item) => item.id)
}

function outfitIsPreferred(outfit: OutfitRecommendation): boolean {
  return likedOutfitIds.value.has(outfit.id) || isPreferred(outfitItemIds(outfit))
}

function outfitIsFavorited(outfit: OutfitRecommendation): boolean {
  const itemIds = outfitItemIds(outfit)
  return itemIds.length === 1
    ? favoriteItemIds.value.has(itemIds[0])
    : isOutfitFavorited(itemIds)
}

async function togglePreference(outfit: OutfitRecommendation) {
  if (actionLoading.value) return
  const itemIds = outfitItemIds(outfit)
  if (isPreferred(itemIds)) {
    await runAction(async () => {
      await deactivatePreferenceOrigin(itemIds)
      preferenceStatus.value = '這套搭配的偏好已停用，可在「我的偏好」重新啟用。'
      emit('preferenceUpdated')
    })
    return
  }

  const next = new Set(likedOutfitIds.value)
  next.has(outfit.id) ? next.delete(outfit.id) : next.add(outfit.id)
  likedOutfitIds.value = next
  proposal.value = null
  preferenceStatus.value = ''

  if (next.size > 0) await buildProposal(next)
}

async function toggleFavorite(outfit: OutfitRecommendation) {
  if (actionLoading.value) return
  const itemIds = outfitItemIds(outfit)
  await runAction(async () => {
    const favorited = !outfitIsFavorited(outfit)
    if (itemIds.length === 1) {
      await setFavoriteItems(itemIds, favorited)
    } else {
      await setFavoriteOutfit(itemIds, favorited)
    }
  })
}

async function buildProposal(selectedIds = likedOutfitIds.value) {
  await runAction(async () => {
    const likedOutfits = [
      ...recommendations.value,
      ...discardedRecommendations.value,
    ].filter((outfit) => selectedIds.has(outfit.id))
    proposal.value = await proposeSoftFromOutfit(
      props.userKey,
      likedOutfits.map((outfit) => outfit.items.map((item) => item.id)),
      originalRequest.value,
      requirements.value,
    )
    await nextTick()
    proposalArea.value?.scrollIntoView({
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      block: 'start',
    })
  })
}

function dismissProposal() {
  proposal.value = null
  likedOutfitIds.value = new Set()
}

async function confirmProposal() {
  if (!proposal.value) return
  await runAction(async () => {
    await confirmPreferences(proposal.value!.proposals)
    proposal.value = null
    likedOutfitIds.value = new Set()
    preferenceStatus.value = '偏好已更新，下次規劃穿搭時會參考這次的選擇。'
    emit('preferenceUpdated')
  })
}

onBeforeUnmount(() => cancelAgentRequest(false))
</script>

<template>
  <section class="agent-view">
    <aside class="chat-panel">
      <header class="chat-header">
        <div class="agent-avatar"><Sparkles :size="18" /></div>
        <div class="agent-heading">
          <strong>Outfit Agent</strong>
          <span :class="{ thinking: agentBusy }" aria-live="polite">
            {{ agentBusy ? '正在思考' : 'Online' }}
          </span>
        </div>
        <button
          class="new-chat-button"
          type="button"
          title="開啟新對話"
          aria-label="開啟新對話"
          :disabled="actionLoading"
          @click="startNewConversation"
        >
          <MessageSquarePlus :size="18" />
        </button>
      </header>

      <div class="message-list-wrap">
        <div
          ref="messageList"
          class="message-list"
          aria-live="polite"
          aria-relevant="additions text"
          @scroll="handleMessageScroll"
        >
          <div v-for="message in messages" :key="message.id" class="message" :class="message.role">
            <span v-if="message.role === 'agent'" class="message-avatar"><Sparkles :size="13" /></span>
            <p>{{ message.text }}</p>
          </div>

          <div
            v-if="typingVisible"
            class="message agent typing-message"
            role="status"
            :aria-label="activityLabel"
          >
            <span class="message-avatar"><Sparkles :size="13" /></span>
            <div class="typing-bubble">
              <span class="typing-label">{{ activityLabel }}</span>
              <span class="typing-dots" aria-hidden="true">
                <i></i><i></i><i></i>
              </span>
            </div>
          </div>

          <div v-if="requestError" class="message agent error-message" role="alert">
            <span class="message-avatar error-avatar"><AlertCircle :size="13" /></span>
            <div>
              <strong>這次沒有完成</strong>
              <p>{{ requestError.message }}</p>
              <button type="button" :disabled="agentBusy" @click="retryAgentRequest">
                <RotateCcw :size="14" />重試
              </button>
            </div>
          </div>

          <p v-if="stoppedNotice" class="chat-system-notice" role="status">
            {{ stoppedNotice }}
          </p>
        </div>

        <button
          v-if="hasUnreadMessage"
          class="new-message-button"
          type="button"
          @click="scrollConversation(true)"
        >
          <ChevronDown :size="14" />有新訊息
        </button>
      </div>

      <div class="chat-composer" :class="{ 'has-confirm': stage === 'start' && hasUserDetails }">
        <div class="audience-control">
          <label for="outfit-audience">服裝受眾</label>
          <select id="outfit-audience" v-model="audience" :disabled="agentBusy">
            <option value="">依需求判斷</option>
            <option value="women">女裝</option>
            <option value="men">男裝</option>
            <option value="unisex">不限性別</option>
          </select>
        </div>
        <textarea
          v-model="draft"
          rows="3"
          :placeholder="composerPlaceholder"
          :disabled="stage === 'results'"
          aria-label="輸入穿搭需求"
          @keydown.ctrl.enter="sendRequest()"
        />
        <button
          v-if="agentBusy"
          class="send-button stop-button"
          type="button"
          title="停止目前操作"
          aria-label="停止目前操作"
          @click="stopAgentRequest"
        >
          <Square :size="14" fill="currentColor" />
        </button>
        <button
          v-else
          class="send-button"
          type="button"
          title="送出"
          aria-label="送出訊息"
          :disabled="!draft.trim() || stage === 'results'"
          @click="sendRequest()"
        >
          <Send :size="18" />
        </button>
        <button
          v-if="stage === 'start' && hasUserDetails"
          class="confirm-requirements-button"
          type="button"
          :disabled="agentBusy"
          @click="confirmRequirements"
        >
          <Check :size="16" />{{ readyToPlan ? '產生搜尋 query' : '不再補充，產生 query' }}
        </button>
      </div>
      <p v-if="actionError" class="chat-error" role="alert">{{ actionError }}</p>
    </aside>

    <main class="agent-workspace">
      <details v-if="requirements?.weather" class="debug-panel" open>
        <summary>搭配參考天氣：{{ requirements.weather.location }}／{{ requirements.weather.target_date }}</summary>
        <p v-if="requirements.weather.status === 'available'">
          氣溫 {{ requirements.weather.temperature_min_c }}～{{ requirements.weather.temperature_max_c }}°C；
          體感 {{ requirements.weather.apparent_temperature_min_c ?? '—' }}～{{ requirements.weather.apparent_temperature_max_c ?? '—' }}°C；
          最高降雨機率 {{ requirements.weather.precipitation_probability_max ?? '—' }}%。
        </p>
        <p>{{ requirements.weather.note }}</p>
        <p v-if="requirements.weather.location_assumed">未指定城市，暫用台北；可在對話補充實際地點。</p>
        <a :href="requirements.weather.source_url" target="_blank" rel="noopener noreferrer">天氣來源：Open-Meteo</a>
      </details>
      <details v-if="planningKnowledge.length" class="debug-panel">
        <summary>本次 query 規劃採用的知識（{{ planningKnowledge.length }} 條）</summary>
        <article v-for="item in planningKnowledge" :key="item.observation_id">
          <p>{{ item.summary }}</p>
          <p v-if="item.evidence">依據：{{ item.evidence }}</p>
          <a :href="item.source_url" target="_blank" rel="noopener noreferrer">{{ item.source_title || item.source_name || item.source_url }}</a>
        </article>
      </details>
      <button class="knowledge-source-button" @click="emit('openKnowledge')">
        <BookOpenText :size="16" />知識來源
      </button>

      <section v-if="showQuerySkeleton" class="agent-workspace-loading query-loading" aria-hidden="true">
        <header class="view-heading compact-heading">
          <div>
            <span class="section-kicker">搜尋規劃</span>
            <h2>{{ agentActivity === 'refining' ? '正在調整搜尋條件' : '正在建立搜尋條件' }}</h2>
            <p>Agent 正在把需求整理成可搜尋的商品條件。</p>
          </div>
          <span class="skeleton-count"></span>
        </header>
        <div class="skeleton-query-stack">
          <article v-for="index in 4" :key="index" class="skeleton-query-row">
            <span class="skeleton-block skeleton-zone"></span>
            <div>
              <span class="skeleton-block skeleton-query-line"></span>
              <span class="skeleton-block skeleton-query-caption"></span>
            </div>
          </article>
        </div>
      </section>

      <section v-else-if="showOutfitSkeleton" class="agent-workspace-loading outfit-loading" aria-hidden="true">
        <header class="view-heading compact-heading">
          <div>
            <span class="section-kicker">Recommendations</span>
            <h2>正在搜尋適合的搭配</h2>
            <p>Agent 正在比對商品、穿搭規則與偏好。</p>
          </div>
        </header>
        <div class="skeleton-outfit-grid">
          <article v-for="index in 4" :key="index" class="skeleton-outfit-card">
            <div class="skeleton-outfit-image skeleton-block"></div>
            <div class="skeleton-outfit-copy">
              <span class="skeleton-block skeleton-short-line"></span>
              <span class="skeleton-block skeleton-title-line"></span>
              <span class="skeleton-block skeleton-copy-line"></span>
              <span class="skeleton-block skeleton-copy-line narrow"></span>
            </div>
          </article>
        </div>
      </section>

      <section v-else-if="stage === 'start' && !requirements" class="agent-start">
        <div class="start-icon"><MessageSquare :size="26" /></div>
        <h2>開始新的穿搭搜尋</h2>
        <div class="quick-prompts">
          <button
            v-for="prompt in quickPrompts"
            :key="prompt"
            :disabled="agentBusy"
            @click="sendRequest(prompt)"
          >
            {{ prompt }}
          </button>
        </div>
      </section>

      <section v-else-if="stage === 'start'" class="requirement-review">
        <header class="view-heading compact-heading">
          <div>
            <span class="section-kicker">Requirement check</span>
            <h2>確認穿搭需求</h2>
            <p>繼續在左側回答 Agent，或直接確認並產生搜尋 query。</p>
          </div>
        </header>
        <dl class="requirement-summary">
          <div
            v-for="(label, field) in requirementLabels"
            :key="field"
            :class="{ missing: missingFields.includes(field) }"
          >
            <dt>{{ label }}<small v-if="requirements?.defaulted_fields.includes(field)">（預設，可更改）</small></dt>
            <dd>{{ requirementValue(field) }}</dd>
          </div>
        </dl>
        <button class="primary-button requirement-confirm" :disabled="agentBusy" @click="confirmRequirements">
          <Check :size="17" />{{ readyToPlan ? '確認並產生搜尋 query' : '不再補充，直接產生 query' }}
        </button>
      </section>

      <QueryReview
        v-else-if="stage === 'review'"
        :queries="queries"
        :loading="agentBusy"
        @select="setSelected"
        @update-text="updateQueryText"
        @search="searchOutfits"
      />

      <section v-else class="recommendations-view">
        <header class="view-heading compact-heading">
          <div>
            <button class="back-button" @click="stage = 'review'"><ArrowLeft :size="16" />調整 query</button>
            <span class="section-kicker">Recommendations</span>
            <h2>推薦搭配</h2>
            <p>{{ recommendations.length }} 組結果 · {{ selectedCount }} 個搜尋條件</p>
          </div>
        </header>

        <div v-if="proposal || preferenceStatus" ref="proposalArea" class="preference-confirmation-area">
          <PreferenceProposalPanel
            v-if="proposal"
            :proposal="proposal"
            :loading="actionLoading"
            @confirm="confirmProposal"
            @dismiss="dismissProposal"
          />
          <div v-else class="preference-update-status">
            <Check :size="17" />
            <span>{{ preferenceStatus }}</span>
          </div>
        </div>

        <div v-if="recommendations.length" class="recommendation-grid">
          <OutfitCard
            v-for="outfit in recommendations"
            :key="outfit.id"
            :outfit="outfit"
            :preferred="outfitIsPreferred(outfit)"
            :favorited="outfitIsFavorited(outfit)"
            :action-loading="actionLoading"
            :user-request="originalRequest"
            :styling-guide="stylingGuide"
            :queries="queries"
            @toggle-preference="togglePreference(outfit)"
            @toggle-favorite="toggleFavorite(outfit)"
          />
        </div>
        <div v-else class="empty-view">
          <MessageSquare :size="32" />
          <h3>沒有找到可組合的搭配</h3>
          <button class="secondary-button" @click="stage = 'review'">返回調整 query</button>
        </div>

        <section v-if="discardedRecommendations.length" class="discarded-outfits">
          <button
            class="discarded-toggle"
            type="button"
            :aria-expanded="showDiscarded"
            @click="showDiscarded = !showDiscarded"
          >
            <span>
              {{ showDiscarded ? '收合其他候選搭配' : `查看其他 ${discardedRecommendations.length} 套候選搭配` }}
            </span>
            <ChevronUp v-if="showDiscarded" :size="17" />
            <ChevronDown v-else :size="17" />
          </button>
          <div v-if="showDiscarded" class="recommendation-grid discarded-grid">
            <OutfitCard
              v-for="outfit in discardedRecommendations"
              :key="outfit.id"
              :outfit="outfit"
              :user-request="originalRequest"
              :styling-guide="stylingGuide"
              :queries="queries"
              :preferred="outfitIsPreferred(outfit)"
              :favorited="outfitIsFavorited(outfit)"
              :action-loading="actionLoading"
              @toggle-preference="togglePreference(outfit)"
              @toggle-favorite="toggleFavorite(outfit)"
            />
          </div>
        </section>
      </section>
    </main>
  </section>
</template>
