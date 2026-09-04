<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import {
  ArrowLeft, BookOpenText, Check, ChevronDown, ChevronUp, MessageSquare,
  MessageSquarePlus, Send, Sparkles,
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
  OutfitRecommendation,
  QueryDraft,
  RequirementSummary,
  StylingGuide,
  FashionIntent,
  PipelineDebugSession,
  QueryPlanDebug,
  RecommendationDebug,
  StylePreferenceProposal,
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
const loading = ref(false)
const error = ref('')
const stage = ref<'start' | 'review' | 'results'>('start')
const originalRequest = ref('')
const audience = ref<Audience | ''>('')
const requirements = ref<RequirementSummary | null>(null)
const stylingGuide = ref<StylingGuide | null>(null)
const fashionIntent = ref<FashionIntent | null>(null)
const planDebug = ref<QueryPlanDebug | null>(null)
const recommendationDebug = ref<RecommendationDebug | null>(null)
const reviewNote = ref('')
const knowledgeNote = ref('')
const missingFields = ref<string[]>([])
const readyToPlan = ref(false)
let messageId = 2

const selectedCount = computed(() => queries.value.filter((query) => query.selected).length)
const hasUserDetails = computed(() => messages.value.some((message) => message.role === 'user'))
const composerPlaceholder = computed(() => {
  if (stage.value === 'start') return '回答 Agent 的問題，或補充你的穿搭需求'
  if (stage.value === 'review') return '補充調整，例如：不要裙子、再正式一點'
  return '若要搜尋其他穿搭，請開啟新的對話'
})

type RequirementDisplayField = Exclude<
  keyof RequirementSummary,
  'search_brief' | 'tag_translations'
>

const requirementLabels: Record<RequirementDisplayField, string> = {
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

function requirementValue(field: RequirementDisplayField): string {
  const value = requirements.value?.[field]
  if (Array.isArray(value)) {
    return value.length
      ? value.map((tag) => requirements.value?.tag_translations[tag] || tag).join('、')
      : '尚未提供'
  }
  return value?.trim() || '尚未提供'
}

const quickPrompts = [
  '適合上班的簡約藍色穿搭，預算 3000 元',
  '週末休閒穿搭，不要裙子',
  '想找粉色的夏季洋裝',
]

function addMessage(role: 'agent' | 'user', text: string) {
  messages.value.push({ id: messageId++, role, text })
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

async function run(task: () => Promise<void>) {
  loading.value = true
  error.value = ''
  try {
    await task()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '發生未知錯誤'
  } finally {
    loading.value = false
  }
}

async function sendRequest(text = draft.value) {
  const content = text.trim()
  if (!content || loading.value) return
  if (stage.value === 'results') return
  draft.value = ''
  addMessage('user', content)
  if (stage.value === 'review') {
    await refine(content)
    return
  }
  await run(async () => {
    const response = await clarifyRequirements(
      messages.value.map(({ role, text }) => ({ role, text })),
      props.userKey,
      requirements.value,
      audience.value || undefined,
    )
    requirements.value = response.requirements
    missingFields.value = response.missing_fields
    readyToPlan.value = response.ready_to_plan
    addMessage('agent', response.reply)
    publishDebug()
  })
}

async function refine(text: string) {
  const previousRequest = originalRequest.value
  await run(async () => {
    const response = await refineQueryPlan(
      text,
      props.userKey,
      queries.value,
      previousRequest,
      requirements.value,
      fashionIntent.value,
      audience.value || undefined,
    )
    queries.value = response.queries
    stylingGuide.value = response.styling_guide
    fashionIntent.value = response.fashion_intent
    planDebug.value = response.debug
    recommendationDebug.value = null
    audience.value = response.audience ?? audience.value
    originalRequest.value = `${previousRequest} ${text}`.trim()
    addMessage('agent', `已依照補充條件重新規劃 ${response.queries.length} 個搜尋條件。`)
    publishDebug()
  })
}

async function confirmRequirements() {
  if (!hasUserDetails.value || loading.value) return
  const rawUserRequest = messages.value
    .filter((message) => message.role === 'user')
    .map((message) => message.text)
    .join('；')
    .trim()
  const planningInput = rawUserRequest || requirements.value?.search_brief.trim() || ''
  originalRequest.value = planningInput
  await run(async () => {
    const response = await createQueryPlan(
      planningInput,
      props.userKey,
      requirements.value,
      audience.value || undefined,
    )
    queries.value = response.queries
    stylingGuide.value = response.styling_guide
    fashionIntent.value = response.fashion_intent
    planDebug.value = response.debug
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
  })
}

function startNewConversation() {
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
  recommendationDebug.value = null
  reviewNote.value = ''
  knowledgeNote.value = ''
  missingFields.value = []
  readyToPlan.value = false
  originalRequest.value = ''
  likedOutfitIds.value = new Set()
  proposal.value = null
  preferenceStatus.value = ''
  error.value = ''
  stage.value = 'start'
}

async function searchOutfits() {
  await run(async () => {
    const response = await getRecommendations(
      queries.value,
      props.userKey,
      originalRequest.value,
      requirements.value,
      stylingGuide.value,
      audience.value || undefined,
    )
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
      `找到 ${response.recommendations.length} 組搭配，使用 ${response.knowledge_observation_count} 條文章知識。${response.aesthetic_reviewed ? '已完成圖片美感審查。' : response.review_note}`,
    )
    publishDebug()
  })
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
  if (loading.value) return
  const itemIds = outfitItemIds(outfit)
  if (isPreferred(itemIds)) {
    await run(async () => {
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
  if (loading.value) return
  const itemIds = outfitItemIds(outfit)
  await run(async () => {
    const favorited = !outfitIsFavorited(outfit)
    if (itemIds.length === 1) {
      await setFavoriteItems(itemIds, favorited)
    } else {
      await setFavoriteOutfit(itemIds, favorited)
    }
  })
}

async function buildProposal(selectedIds = likedOutfitIds.value) {
  await run(async () => {
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
    proposalArea.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function dismissProposal() {
  proposal.value = null
  likedOutfitIds.value = new Set()
}

async function confirmProposal() {
  if (!proposal.value) return
  await run(async () => {
    await confirmPreferences(proposal.value!.proposals)
    proposal.value = null
    likedOutfitIds.value = new Set()
    preferenceStatus.value = '偏好已更新，下次規劃穿搭時會參考這次的選擇。'
    emit('preferenceUpdated')
  })
}
</script>

<template>
  <section class="agent-view">
    <aside class="chat-panel">
      <header class="chat-header">
        <div class="agent-avatar"><Sparkles :size="18" /></div>
        <div><strong>Outfit Agent</strong><span>Online</span></div>
        <button class="new-chat-button" title="開啟新對話" @click="startNewConversation">
          <MessageSquarePlus :size="18" />
        </button>
      </header>

      <div class="message-list">
        <div v-for="message in messages" :key="message.id" class="message" :class="message.role">
          <span v-if="message.role === 'agent'" class="message-avatar"><Sparkles :size="13" /></span>
          <p>{{ message.text }}</p>
        </div>

      </div>

      <div class="chat-composer" :class="{ 'has-confirm': stage === 'start' && hasUserDetails }">
        <div class="audience-control">
          <label for="outfit-audience">服裝受眾</label>
          <select id="outfit-audience" v-model="audience">
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
          @keydown.ctrl.enter="sendRequest()"
        />
        <button class="send-button" title="送出" :disabled="loading || !draft.trim() || stage === 'results'" @click="sendRequest()">
          <Send :size="18" />
        </button>
        <button
          v-if="stage === 'start' && hasUserDetails"
          class="confirm-requirements-button"
          :disabled="loading"
          @click="confirmRequirements"
        >
          <Check :size="16" />{{ readyToPlan ? '產生搜尋 query' : '不再補充，產生 query' }}
        </button>
      </div>
      <p v-if="error" class="chat-error">{{ error }}</p>
    </aside>

    <main class="agent-workspace">
      <button class="knowledge-source-button" @click="emit('openKnowledge')">
        <BookOpenText :size="16" />知識來源
      </button>

      <section v-if="stage === 'start' && !requirements" class="agent-start">
        <div class="start-icon"><MessageSquare :size="26" /></div>
        <h2>開始新的穿搭搜尋</h2>
        <div class="quick-prompts">
          <button v-for="prompt in quickPrompts" :key="prompt" @click="sendRequest(prompt)">{{ prompt }}</button>
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
            <dt>{{ label }}</dt>
            <dd>{{ requirementValue(field) }}</dd>
          </div>
        </dl>
        <button class="primary-button requirement-confirm" :disabled="loading" @click="confirmRequirements">
          <Check :size="17" />{{ readyToPlan ? '確認並產生搜尋 query' : '不再補充，直接產生 query' }}
        </button>
      </section>

      <QueryReview
        v-else-if="stage === 'review'"
        :queries="queries"
        :loading="loading"
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
            :loading="loading"
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
            v-for="(outfit, index) in recommendations"
            :key="outfit.id"
            :outfit="outfit"
            :rank="index + 1"
            :preferred="outfitIsPreferred(outfit)"
            :favorited="outfitIsFavorited(outfit)"
            :action-loading="loading"
            :featured="index === 0"
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
              v-for="(outfit, index) in discardedRecommendations"
              :key="outfit.id"
              :outfit="outfit"
              :rank="recommendations.length + index + 1"
              :user-request="originalRequest"
              :styling-guide="stylingGuide"
              :queries="queries"
              :preferred="outfitIsPreferred(outfit)"
              :favorited="outfitIsFavorited(outfit)"
              :action-loading="loading"
              @toggle-preference="togglePreference(outfit)"
              @toggle-favorite="toggleFavorite(outfit)"
            />
          </div>
        </section>
      </section>
    </main>
  </section>
</template>
