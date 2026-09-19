<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Bookmark, BookOpenText, ChevronDown, Compass, Fingerprint, Images, LogOut, MessageSquareText,
  ScanFace, Search, Shirt, SlidersHorizontal, Sparkles, UserRound,
} from 'lucide-vue-next'
import AgentSearchView from './views/AgentSearchView.vue'
import SimilarSearchView from './views/SimilarSearchView.vue'
import CatalogView from './views/CatalogView.vue'
import FashionMbtiView from './views/FashionMbtiView.vue'
import FavoritesView from './views/FavoritesView.vue'
import WardrobeView from './views/WardrobeView.vue'
import PreferencesView from './views/PreferencesView.vue'
import VirtualTryOnView from './views/VirtualTryOnView.vue'
import KnowledgeManagementView from './views/KnowledgeManagementView.vue'
import DebugPipelineView from './views/DebugPipelineView.vue'
import type { AppView, PipelineDebugSession, TryOnDraft } from './types'
import { useUserLibrary } from './composables/useUserLibrary'
import { useDebugHistory } from './composables/useDebugHistory'

const props = defineProps<{ userKey: string }>()
const emit = defineEmits<{ logout: [] }>()

const route = useRoute()
const router = useRouter()
const activeView = computed<AppView>(() => (route.name as AppView | undefined) ?? 'agent')
const preferenceRevision = ref(0)
const tryOnDraft = ref<TryOnDraft | null>(null)
const analysisOpen = ref(false)
let tryOnDraftRevision = 0
const debugTrace = ref<PipelineDebugSession | null>(null)
const debugHistory = useDebugHistory(props.userKey)
function updateDebug(trace: PipelineDebugSession) {
  debugTrace.value = trace
  debugHistory.save(trace)
}
const { loadLibrary } = useUserLibrary(props.userKey)

const navGroups = [
  {
    id: 'features',
    label: '穿搭功能',
    icon: Sparkles,
    items: [
      { id: 'agent' as const, label: '找搭配', icon: MessageSquareText },
      { id: 'similarity' as const, label: '找相似', icon: Search },
      { id: 'tryon' as const, label: '虛擬試穿', icon: ScanFace },
    ],
  },
  {
    id: 'browse',
    label: '品項總覽',
    icon: Compass,
    items: [
      { id: 'catalog' as const, label: '衣服商品', icon: Shirt },
      { id: 'knowledge' as const, label: '穿搭文章', icon: BookOpenText },
    ],
  },
  {
    id: 'mine',
    label: '個人中心',
    icon: UserRound,
    items: [
      { id: 'wardrobe' as const, label: '我的衣櫃', icon: Images },
      { id: 'favorites' as const, label: '我的收藏', icon: Bookmark },
      { id: 'preferences' as const, label: '我的偏好', icon: SlidersHorizontal },
    ],
  },
]
const standaloneNav = [
  { id: 'mbti' as const, label: '穿搭測試', icon: Fingerprint },
]

const navRef = ref<HTMLElement | null>(null)
const userMenuRef = ref<HTMLElement | null>(null)
const openGroupId = ref<string | null>(null)
const userMenuOpen = ref(false)

const avatarInitial = props.userKey.trim().charAt(0).toUpperCase() || '?'

function isGroupActive(group: (typeof navGroups)[number]) {
  return group.items.some(item => item.id === activeView.value)
}
function openGroup(id: string) {
  userMenuOpen.value = false
  openGroupId.value = id
}
function closeGroup(id: string) {
  if (openGroupId.value === id) openGroupId.value = null
}
function toggleGroup(id: string) {
  userMenuOpen.value = false
  openGroupId.value = openGroupId.value === id ? null : id
}
function handleGroupPointerEnter(id: string) {
  if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) openGroup(id)
}
function handleGroupTriggerClick(event: MouseEvent, id: string) {
  const isMouseClick = event.detail > 0
  if (isMouseClick && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    openGroup(id)
    return
  }
  toggleGroup(id)
}
function handleGroupFocusOut(event: FocusEvent, id: string) {
  const group = event.currentTarget
  const nextTarget = event.relatedTarget
  if (group instanceof HTMLElement && nextTarget instanceof Node && group.contains(nextTarget)) return
  closeGroup(id)
}
function handleGroupEscape(event: KeyboardEvent, id: string) {
  closeGroup(id)
  if (event.currentTarget instanceof HTMLElement) {
    event.currentTarget.querySelector<HTMLButtonElement>('.nav-group-trigger')?.focus()
  }
}
function selectView(id: AppView) {
  analysisOpen.value = false
  if (route.name !== id) void router.push({ name: id })
  openGroupId.value = null
}
async function openAnalysis() {
  const latest = debugHistory.history.value[0]
  if (latest) await debugHistory.select(latest.id)
  else debugHistory.showCurrent()
  analysisOpen.value = true
}
function startTryOn(draft: TryOnDraft) {
  tryOnDraftRevision += 1
  tryOnDraft.value = { ...draft, revision: tryOnDraftRevision }
  if (route.name !== 'tryon') void router.push({ name: 'tryon' })
  openGroupId.value = null
}
function toggleUserMenu() {
  openGroupId.value = null
  userMenuOpen.value = !userMenuOpen.value
}
function handleLogout() {
  userMenuOpen.value = false
  emit('logout')
}
function handleDocumentClick(event: MouseEvent) {
  const target = event.target as Node
  if (openGroupId.value && navRef.value && !navRef.value.contains(target)) {
    openGroupId.value = null
  }
  if (userMenuOpen.value && userMenuRef.value && !userMenuRef.value.contains(target)) {
    userMenuOpen.value = false
  }
}

onMounted(() => {
  void debugHistory.load()
  void loadLibrary().catch(() => undefined)
  document.addEventListener('click', handleDocumentClick)
})
onBeforeUnmount(() => document.removeEventListener('click', handleDocumentClick))
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <button class="brand" title="潮會搭" @click="selectView('agent')">
        <div><strong>潮會搭</strong><small>個人穿搭</small></div>
      </button>

      <nav ref="navRef" class="main-navigation" aria-label="主要功能">
        <div
          v-for="group in navGroups"
          :key="group.id"
          class="nav-group"
          @mouseenter="handleGroupPointerEnter(group.id)"
          @mouseleave="closeGroup(group.id)"
          @focusin="openGroup(group.id)"
          @focusout="handleGroupFocusOut($event, group.id)"
          @keydown.esc.stop="handleGroupEscape($event, group.id)"
        >
          <button
            class="nav-top-button nav-group-trigger"
            :class="{ active: isGroupActive(group) }"
            aria-haspopup="true"
            :aria-expanded="openGroupId === group.id"
            :aria-controls="`nav-menu-${group.id}`"
            @click="handleGroupTriggerClick($event, group.id)"
          >
            <component :is="group.icon" :size="17" />{{ group.label }}
            <ChevronDown class="nav-caret" :class="{ open: openGroupId === group.id }" :size="14" />
          </button>
          <div v-if="openGroupId === group.id" :id="`nav-menu-${group.id}`" class="nav-dropdown">
            <button
              v-for="item in group.items"
              :key="item.id"
              :class="{ active: activeView === item.id }"
              @click="selectView(item.id)"
            >
              <component :is="item.icon" :size="16" />{{ item.label }}
            </button>
          </div>
        </div>
        <button
          v-for="item in standaloneNav"
          :key="item.id"
          class="nav-top-button"
          :class="{ active: activeView === item.id }"
          @click="selectView(item.id)"
        >
          <component :is="item.icon" :size="17" />{{ item.label }}
        </button>
      </nav>

      <div ref="userMenuRef" class="nav-group user-menu-group">
        <button class="user-menu" title="目前登入使用者" @click="toggleUserMenu">
          <span>{{ avatarInitial }}</span><div><strong>{{ userKey }}</strong></div>
        </button>
        <div v-if="userMenuOpen" class="nav-dropdown align-right">
          <button @click="handleLogout">
            <LogOut :size="16" />登出
          </button>
        </div>
      </div>
    </header>

    <div class="app-content">
      <AgentSearchView
        v-show="activeView === 'agent' && !analysisOpen"
        :user-key="userKey"
        @preference-updated="preferenceRevision++"
        @debug-updated="updateDebug"
        @open-analysis="openAnalysis"
      />
      <DebugPipelineView
        v-if="activeView === 'agent' && analysisOpen"
        :trace="debugHistory.selected.value ?? debugTrace"
        :history="debugHistory.history.value"
        :selected-id="debugHistory.selectedId.value"
        @select-history="debugHistory.select"
        @show-current="debugHistory.showCurrent"
        @delete-history="debugHistory.remove"
        @back="analysisOpen = false"
      />
      <KnowledgeManagementView v-if="activeView === 'knowledge'" />
      <SimilarSearchView v-show="activeView === 'similarity'" />
      <CatalogView v-show="activeView === 'catalog'" :user-key="userKey" />
      <WardrobeView v-if="activeView === 'wardrobe'" :user-key="userKey" />
      <FavoritesView
        v-show="activeView === 'favorites'"
        :user-key="userKey"
        @start-try-on="startTryOn"
      />
      <VirtualTryOnView
        v-show="activeView === 'tryon'"
        :user-key="userKey"
        :draft="tryOnDraft"
      />
      <FashionMbtiView v-if="activeView === 'mbti'" :user-key="userKey" />
      <PreferencesView
        v-show="activeView === 'preferences'"
        :key="preferenceRevision"
        :user-key="userKey"
      />
    </div>
  </div>
</template>
