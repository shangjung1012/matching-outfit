<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import {
  ArrowLeft, Check, ChevronDown, ChevronUp,
  FileSearch, ImagePlus, MessageSquare, MessageSquarePlus, Send, Shirt,
  Sparkles, Square, X,
} from 'lucide-vue-next'
import {
  clarifyRequirements,
  createQueryPlan,
  getRecommendations,
  refineQueryPlan,
} from '../api'
import OutfitCard from '../components/OutfitCard.vue'
import QueryReview from '../components/QueryReview.vue'
import { useUserLibrary } from '../composables/useUserLibrary'
import { useToast } from '../composables/useToast'
import type {
  FashionObservationTrace,
  FashionIntent,
  OutfitRecommendation,
  PipelineDebugSession,
  QueryDraft,
  QueryPlanDebug,
  PlannerGarmentZone,
  RecommendationDebug,
  RequirementSummary,
  ShoeSpec,
  StylingGuide,
} from '../types'

const props = defineProps<{ userKey: string }>()
const emit = defineEmits<{
  preferenceUpdated: []
  debugUpdated: [trace: PipelineDebugSession]
  openAnalysis: []
}>()
const {
  favoriteItemIds,
  isOutfitFavorited,
  setFavoriteItems,
  setFavoriteOutfit,
  outfitPreference,
  addOutfitReaction,
  removePreference,
} = useUserLibrary(props.userKey)
const { showError, showInfo } = useToast()

interface ChatMessage {
  id: number
  role: 'agent' | 'user'
  text: string
}

type AgentActivityKind = 'clarifying' | 'planning' | 'refining' | 'searching'

const activityLabels: Record<AgentActivityKind, string> = {
  clarifying: '正在理解你的需求',
  planning: '正在準備搭配方向',
  refining: '正在調整搭配方向',
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
const messageList = ref<HTMLElement | null>(null)
const composerInput = ref<HTMLTextAreaElement | null>(null)
const agentActivity = ref<AgentActivityKind | null>(null)
const typingVisible = ref(false)
const actionLoading = ref(false)
const isNearMessageBottom = ref(true)
const hasUnreadMessage = ref(false)
const stage = ref<'start' | 'review' | 'results'>('start')
const originalRequest = ref('')
const requirements = ref<RequirementSummary | null>(null)
const stylingGuide = ref<StylingGuide | null>(null)
const shoeSpecs = ref<Record<string, ShoeSpec>>({})
const fashionIntent = ref<FashionIntent | null>(null)
const planDebug = ref<QueryPlanDebug | null>(null)
const planningKnowledge = ref<FashionObservationTrace[]>([])
const recommendationDebug = ref<RecommendationDebug | null>(null)
const reviewNote = ref('')
const knowledgeNote = ref('')
const missingFields = ref<string[]>([])
const readyToPlan = ref(false)
const referenceImage = ref<File | null>(null)
const referenceType = ref<'upper_body' | 'lower_body'>('upper_body')
const referencePreviewUrl = ref('')
const referencePickerOpen = ref(false)
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

function chooseReferenceImage(event: Event) {
  const input = event.target as HTMLInputElement
  const image = input.files?.[0] ?? null
  if (referencePreviewUrl.value) URL.revokeObjectURL(referencePreviewUrl.value)
  referenceImage.value = image
  referencePreviewUrl.value = image ? URL.createObjectURL(image) : ''
}

function clearReferenceImage() {
  if (referencePreviewUrl.value) URL.revokeObjectURL(referencePreviewUrl.value)
  referenceImage.value = null
  referencePreviewUrl.value = ''
}

function focusComposer() {
  void nextTick(() => composerInput.value?.focus())
}

function requestedCatalogZones(): PlannerGarmentZone[] | null {
  if (!referenceImage.value) return null
  return [referenceType.value === 'upper_body' ? 'lower_body' : 'upper_body']
}

type RequirementDisplayField = Exclude<
  keyof RequirementSummary,
  'search_brief' | 'tag_translations' | 'defaulted_fields' | 'weather'
>

const requirementLabels: Record<RequirementDisplayField, string> = {
  location: '地點',
  target_date: '日期（台灣時間）',
  outfit_budget_max: '整套預算上限',
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
  if (field === 'outfit_budget_max') {
    return typeof value === 'number'
      ? `NT$ ${value.toLocaleString('zh-TW')} 內（整套）`
      : '尚未提供'
  }
  if (Array.isArray(value)) {
    return value.length
      ? value.map((tag) => requirements.value?.tag_translations[tag] || tag).join('、')
      : '尚未提供'
  }
  return typeof value === 'string' && value.trim() ? value.trim() : '尚未提供'
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
  if (showNotice) {
    showInfo('已停止目前操作。你的草稿仍保留，可以修改後再送出。')
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
    showError(errorMessage(reason), {
      action: {
        label: '重試',
        onClick: () => { if (!agentBusy.value) void retry() },
      },
    })
  } finally {
    if (sequence === requestSequence) {
      clearTypingTimer()
      activeController = null
      agentActivity.value = null
      typingVisible.value = false
    }
  }
}

async function runAction(task: () => Promise<void>) {
  if (actionLoading.value) return
  actionLoading.value = true
  try {
    await task()
  } catch (reason) {
    showError(errorMessage(reason))
  } finally {
    actionLoading.value = false
  }
}

async function requestClarification(
  chatMessages: Array<{ role: 'agent' | 'user'; text: string }>,
  previousRequirements: RequirementSummary | null,
) {
  const retry = () => requestClarification(chatMessages, previousRequirements)
  await runAgentRequest(
    'clarifying',
    (signal) => clarifyRequirements(
      chatMessages,
      props.userKey,
      previousRequirements,
      undefined,
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
) {
  const retry = () => requestRefinement(
    text,
    existingQueries,
    previousRequest,
    currentRequirements,
    currentFashionIntent,
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
      undefined,
      requestedCatalogZones(),
      signal,
    ),
    (response) => {
      queries.value = response.queries
      stylingGuide.value = response.styling_guide
      shoeSpecs.value = Object.fromEntries(
        response.shoe_plans.map((plan) => [plan.direction_id, plan.shoe_spec]),
      )
      fashionIntent.value = response.fashion_intent
      planDebug.value = response.debug
      requirements.value = response.debug?.requirement_summary ?? requirements.value
      planningKnowledge.value = response.knowledge_observations ?? []
      recommendationDebug.value = null
      originalRequest.value = `${previousRequest} ${text}`.trim()
      addMessage('agent', `已依照補充內容調整 ${response.queries.length} 個搭配方向。`)
      publishDebug()
    },
    retry,
  )
}

async function requestPlanning(
  planningInput: string,
  currentRequirements: RequirementSummary | null,
) {
  const retry = () => requestPlanning(planningInput, currentRequirements)
  await runAgentRequest(
    'planning',
    (signal) => createQueryPlan(
      planningInput,
      props.userKey,
      currentRequirements,
      undefined,
      requestedCatalogZones(),
      signal,
    ),
    (response) => {
      originalRequest.value = planningInput
      queries.value = response.queries
      stylingGuide.value = response.styling_guide
      shoeSpecs.value = Object.fromEntries(
        response.shoe_plans.map((plan) => [plan.direction_id, plan.shoe_spec]),
      )
      fashionIntent.value = response.fashion_intent
      planDebug.value = response.debug
      requirements.value = response.debug?.requirement_summary ?? requirements.value
      planningKnowledge.value = response.knowledge_observations ?? []
      recommendationDebug.value = null
      recommendations.value = []
      discardedRecommendations.value = []
      showDiscarded.value = false
      stage.value = 'review'
      addMessage(
        'agent',
        `需求已確認，整理出 ${response.queries.length} 個搭配方向。${response.planning_note}`,
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
) {
  const retry = () => requestRecommendations(
    selectedQueries,
    userInput,
    currentRequirements,
    currentStylingGuide,
  )
  await runAgentRequest(
    'searching',
    (signal) => getRecommendations(
      selectedQueries,
      props.userKey,
      userInput,
      currentRequirements,
      currentStylingGuide,
      shoeSpecs.value,
      undefined,
      signal,
      fashionIntent.value,
      referenceImage.value,
      referenceImage.value ? referenceType.value : null,
    ),
    (response) => {
      recommendations.value = response.recommendations
      discardedRecommendations.value = response.discarded_recommendations
      recommendationDebug.value = response.debug
      reviewNote.value = response.review_note
      knowledgeNote.value = response.knowledge_note
      showDiscarded.value = false
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
    )
    return
  }
  await requestClarification(
    messages.value.map(({ role, text: messageText }) => ({ role, text: messageText })),
    requirements.value,
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
  clearReferenceImage()
  referencePickerOpen.value = false
  missingFields.value = []
  readyToPlan.value = false
  originalRequest.value = ''
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
  )
}

function setSelected(id: string, selected: boolean) {
  const query = queries.value.find((item) => item.id === id)
  if (query) query.selected = selected
  publishDebug()
}

function outfitItemIds(outfit: OutfitRecommendation): number[] {
  return outfit.items.filter((item) => !item.is_reference).map((item) => item.id)
}

function outfitPreferenceType(outfit: OutfitRecommendation) {
  return outfitPreference(outfitItemIds(outfit))?.preference_type ?? null
}

function outfitIsFavorited(outfit: OutfitRecommendation): boolean {
  const itemIds = outfitItemIds(outfit)
  return itemIds.length === 1
    ? favoriteItemIds.value.has(itemIds[0])
    : isOutfitFavorited(itemIds)
}

async function reactToOutfit(
  outfit: OutfitRecommendation,
  preferenceType: 'prefer' | 'avoid',
) {
  if (actionLoading.value) return
  const itemIds = outfitItemIds(outfit)
  const current = outfitPreference(itemIds)
  await runAction(async () => {
    if (current?.preference_type === preferenceType) {
      await removePreference(current.id)
    } else {
      if (current) await removePreference(current.id)
      await addOutfitReaction(
        itemIds,
        originalRequest.value,
        requirements.value,
        preferenceType,
      )
    }
    emit('preferenceUpdated')
  })
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

onBeforeUnmount(() => {
  cancelAgentRequest(false)
  clearReferenceImage()
})
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
        <textarea
          ref="composerInput"
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
          <Check :size="16" />{{ readyToPlan ? '確認需求' : '依目前內容繼續' }}
        </button>
      </div>
    </aside>

    <main class="agent-workspace">
      <div class="analysis-entry-toolbar">
        <button class="secondary-button" type="button" @click="emit('openAnalysis')">
          <FileSearch :size="16" />詳細搭配分析
        </button>
      </div>
      <details v-if="planningKnowledge.length" class="agent-context-details">
        <summary>搭配參考（{{ planningKnowledge.length }}）</summary>
        <article v-for="item in planningKnowledge" :key="item.observation_id">
          <p>{{ item.summary }}</p>
          <a :href="item.source_url" target="_blank" rel="noopener noreferrer">{{ item.source_title || item.source_name || item.source_url }}</a>
        </article>
      </details>

      <section v-if="showQuerySkeleton" class="agent-workspace-loading query-loading" aria-hidden="true">
        <header class="view-heading compact-heading">
          <div>
            <span class="section-kicker">搭配方向</span>
            <h2>{{ agentActivity === 'refining' ? '正在調整搭配方向' : '正在準備搭配方向' }}</h2>
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
        <span class="section-kicker">Find your outfit</span>
        <h2>想怎麼開始？</h2>
        <div class="agent-start-modes">
          <button type="button" :disabled="agentBusy" @click="focusComposer">
            <span class="start-mode-icon"><MessageSquare :size="22" /></span>
            <strong>描述穿搭需求</strong>
            <small>告訴我場合、風格或預算</small>
          </button>
          <button type="button" :disabled="agentBusy" @click="referencePickerOpen = true">
            <img v-if="referencePreviewUrl" :src="referencePreviewUrl" alt="你的單品" />
            <span v-else class="start-mode-icon"><Shirt :size="22" /></span>
            <strong>{{ referenceImage ? '已加入一件單品' : '從我的單品開始' }}</strong>
            <small>{{ referenceImage ? (referenceType === 'upper_body' ? '用這件上衣找下身' : '用這件下身找上衣') : '上傳照片，找出適合的搭配' }}</small>
          </button>
        </div>
        <p class="quick-prompts-title">或從這些需求開始</p>
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
            <span class="section-kicker">Your request</span>
            <h2>確認穿搭需求</h2>
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
          <Check :size="17" />{{ readyToPlan ? '確認需求' : '依目前內容繼續' }}
        </button>
      </section>

      <QueryReview
        v-else-if="stage === 'review'"
        :queries="queries"
        :loading="agentBusy"
        @select="setSelected"
        @search="searchOutfits"
      />

      <section v-else class="recommendations-view">
        <header class="view-heading compact-heading">
          <div>
            <button class="back-button" @click="stage = 'review'"><ArrowLeft :size="16" />調整條件</button>
            <span class="section-kicker">Recommendations</span>
            <h2>推薦搭配</h2>
            <p>{{ recommendations.length }} 組結果 · {{ selectedCount }} 個搭配方向</p>
          </div>
        </header>

        <div v-if="recommendations.length" class="recommendation-grid">
          <OutfitCard
            v-for="outfit in recommendations"
            :key="outfit.id"
            :outfit="outfit"
            :preference-type="outfitPreferenceType(outfit)"
            :favorited="outfitIsFavorited(outfit)"
            :action-loading="actionLoading"
            :user-request="originalRequest"
            :styling-guide="stylingGuide"
            :queries="queries"
            :reference-preview-url="referencePreviewUrl"
            @react="reactToOutfit(outfit, $event)"
            @toggle-favorite="toggleFavorite(outfit)"
          />
        </div>
        <div v-else class="empty-view">
          <MessageSquare :size="32" />
          <h3>沒有找到可組合的搭配</h3>
          <button class="secondary-button" @click="stage = 'review'">返回調整條件</button>
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
              :reference-preview-url="referencePreviewUrl"
              :preference-type="outfitPreferenceType(outfit)"
              :favorited="outfitIsFavorited(outfit)"
              :action-loading="actionLoading"
              @react="reactToOutfit(outfit, $event)"
              @toggle-favorite="toggleFavorite(outfit)"
            />
          </div>
        </section>
      </section>
    </main>

    <div v-if="referencePickerOpen" class="reference-picker-backdrop" @click.self="referencePickerOpen = false">
      <section class="reference-picker" role="dialog" aria-modal="true" aria-labelledby="reference-picker-title">
        <header>
          <div>
            <span class="section-kicker">Start with an item</span>
            <h2 id="reference-picker-title">從我的單品開始</h2>
          </div>
          <button class="icon-button" type="button" title="關閉" @click="referencePickerOpen = false"><X :size="18" /></button>
        </header>
        <div class="reference-type-control" aria-label="單品類型">
          <button type="button" :class="{ active: referenceType === 'upper_body' }" @click="referenceType = 'upper_body'">上衣</button>
          <button type="button" :class="{ active: referenceType === 'lower_body' }" @click="referenceType = 'lower_body'">下身</button>
        </div>
        <label class="reference-dropzone">
          <img v-if="referencePreviewUrl" :src="referencePreviewUrl" alt="你的單品預覽" />
          <span v-else><ImagePlus :size="28" /><strong>選擇單品照片</strong><small>JPG、PNG 或 WebP</small></span>
          <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="agentBusy" @change="chooseReferenceImage" />
        </label>
        <footer>
          <button v-if="referenceImage" class="mbti-text-button" type="button" @click="clearReferenceImage">移除照片</button>
          <button class="primary-button" type="button" :disabled="!referenceImage" @click="referencePickerOpen = false">
            {{ referenceType === 'upper_body' ? '用這件上衣找下身' : '用這件下身找上衣' }}
          </button>
        </footer>
      </section>
    </div>
  </section>
</template>
