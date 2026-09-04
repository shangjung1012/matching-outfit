<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowLeft, Check, Heart, MessageSquare, Send, Sparkles } from 'lucide-vue-next'
import {
  confirmPreferenceProposal,
  createQueryPlan,
  getPreferenceProposal,
  getRecommendations,
  refineQueryPlan,
} from '../api'
import OutfitCard from '../components/OutfitCard.vue'
import PreferenceProposalPanel from '../components/PreferenceProposalPanel.vue'
import QueryReview from '../components/QueryReview.vue'
import type { Audience, OutfitRecommendation, PreferenceProposal, QueryDraft } from '../types'

const props = defineProps<{ userKey: string }>()
const emit = defineEmits<{ preferenceUpdated: [] }>()

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
const likedIds = ref(new Set<number>())
const proposal = ref<PreferenceProposal | null>(null)
const proposalDismissed = ref(false)
const preferenceUpdated = ref(false)
const loading = ref(false)
const error = ref('')
const stage = ref<'start' | 'review' | 'results'>('start')
const originalRequest = ref('')
const audience = ref<Audience | ''>('')
let messageId = 2

const selectedCount = computed(() => queries.value.filter((query) => query.selected).length)
const shouldAskPreference = computed(
  () => stage.value === 'results' && likedIds.value.size > 0 && !proposal.value && !proposalDismissed.value && !preferenceUpdated.value,
)

const quickPrompts = [
  '適合上班的簡約藍色穿搭，預算 3000 元',
  '週末休閒穿搭，不要裙子',
  '想找粉色的夏季洋裝',
]

function addMessage(role: 'agent' | 'user', text: string) {
  messages.value.push({ id: messageId++, role, text })
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
  draft.value = ''
  originalRequest.value = content
  addMessage('user', content)
  await run(async () => {
    const response = await createQueryPlan(content, props.userKey, audience.value || undefined)
    queries.value = response.queries
    audience.value = response.audience ?? audience.value
    recommendations.value = []
    stage.value = 'review'
    addMessage(
      'agent',
      `已參考 ${response.knowledge_observation_ids.length} 條搭配知識並產生 ${response.queries.length} 個搜尋條件。${response.planning_note}`,
    )
  })
}

async function refine(text: string) {
  const previousRequest = originalRequest.value
  addMessage('user', text)
  await run(async () => {
    const response = await refineQueryPlan(
      text,
      props.userKey,
      queries.value,
      previousRequest,
      audience.value || undefined,
    )
    queries.value = response.queries
    audience.value = response.audience ?? audience.value
    originalRequest.value = `${previousRequest} ${text}`.trim()
    addMessage('agent', `已依照補充條件與 ${response.knowledge_observation_ids.length} 條搭配知識重新規劃。`)
  })
}

async function searchOutfits() {
  await run(async () => {
    const response = await getRecommendations(
      queries.value,
      props.userKey,
      originalRequest.value,
      audience.value || undefined,
    )
    recommendations.value = response.recommendations
    likedIds.value = new Set()
    proposal.value = null
    proposalDismissed.value = false
    preferenceUpdated.value = false
    stage.value = 'results'
    addMessage(
      'agent',
      `找到 ${response.recommendations.length} 組搭配，使用 ${response.knowledge_observation_count} 條文章知識。${response.aesthetic_reviewed ? '已完成圖片美感審查。' : response.review_note}`,
    )
  })
}

function setSelected(id: string, selected: boolean) {
  const query = queries.value.find((item) => item.id === id)
  if (query) query.selected = selected
}

function updateQueryText(id: string, text: string) {
  const query = queries.value.find((item) => item.id === id)
  if (query) query.text = text
}

function toggleLike(id: number) {
  const next = new Set(likedIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  likedIds.value = next
  proposal.value = null
  proposalDismissed.value = false
  preferenceUpdated.value = false
}

async function buildProposal() {
  await run(async () => {
    proposal.value = await getPreferenceProposal(props.userKey, [...likedIds.value])
    addMessage('agent', '我整理了這次按愛心反映出的偏好，你可以先確認再更新。')
  })
}

async function confirmProposal() {
  if (!proposal.value) return
  await run(async () => {
    await confirmPreferenceProposal(props.userKey, proposal.value!)
    proposal.value = null
    preferenceUpdated.value = true
    emit('preferenceUpdated')
    addMessage('agent', '偏好已更新，下次拆解需求時會一起參考。')
  })
}
</script>

<template>
  <section class="agent-view">
    <aside class="chat-panel">
      <header class="chat-header">
        <div class="agent-avatar"><Sparkles :size="18" /></div>
        <div><strong>Styling Agent</strong><span>Online</span></div>
      </header>

      <div class="message-list">
        <div v-for="message in messages" :key="message.id" class="message" :class="message.role">
          <span v-if="message.role === 'agent'" class="message-avatar"><Sparkles :size="13" /></span>
          <p>{{ message.text }}</p>
        </div>

        <div v-if="shouldAskPreference" class="message agent action-message">
          <span class="message-avatar"><Heart :size="13" /></span>
          <div>
            <p>你對 {{ likedIds.size }} 件衣服按了愛心，要用這些選擇更新個人偏好嗎？</p>
            <button :disabled="loading" @click="buildProposal">查看更新內容</button>
          </div>
        </div>
        <div v-if="preferenceUpdated" class="message agent status-message">
          <span class="message-avatar"><Check :size="13" /></span><p>這次的偏好已經記下來了。</p>
        </div>
      </div>

      <div class="chat-composer">
        <div class="audience-control">
          <label for="outfit-audience">服裝受眾</label>
          <select id="outfit-audience" v-model="audience">
            <option value="">依需求判斷</option>
            <option value="women">女裝</option>
            <option value="men">男裝</option>
            <option value="unisex">不限性別</option>
          </select>
        </div>
        <textarea v-model="draft" rows="3" placeholder="輸入穿搭需求或補充條件" @keydown.ctrl.enter="sendRequest()" />
        <button class="send-button" title="送出" :disabled="loading || !draft.trim()" @click="sendRequest()">
          <Send :size="18" />
        </button>
      </div>
      <p v-if="error" class="chat-error">{{ error }}</p>
    </aside>

    <main class="agent-workspace">
      <section v-if="stage === 'start'" class="agent-start">
        <div class="start-icon"><MessageSquare :size="26" /></div>
        <h2>開始新的穿搭搜尋</h2>
        <div class="quick-prompts">
          <button v-for="prompt in quickPrompts" :key="prompt" @click="sendRequest(prompt)">{{ prompt }}</button>
        </div>
      </section>

      <QueryReview
        v-else-if="stage === 'review'"
        :queries="queries"
        :loading="loading"
        @select="setSelected"
        @update-text="updateQueryText"
        @refine="refine"
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

        <PreferenceProposalPanel
          v-if="proposal"
          :proposal="proposal"
          :loading="loading"
          @confirm="confirmProposal"
          @dismiss="proposal = null; proposalDismissed = true"
        />

        <div v-if="recommendations.length" class="recommendation-grid">
          <OutfitCard
            v-for="(outfit, index) in recommendations"
            :key="outfit.id"
            :outfit="outfit"
            :rank="index + 1"
            :liked-ids="likedIds"
            :featured="index === 0"
            @toggle-like="toggleLike"
          />
        </div>
        <div v-else class="empty-view">
          <MessageSquare :size="32" />
          <h3>沒有找到可組合的搭配</h3>
          <button class="secondary-button" @click="stage = 'review'">返回調整 query</button>
        </div>
      </section>
    </main>
  </section>
</template>
