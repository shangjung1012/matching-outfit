<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import {
  Bookmark, BookOpenText, Bug, ChevronDown, Compass, Fingerprint, MessageSquareText,
  ScanFace, Search, Shirt, SlidersHorizontal, Sparkles, UserRound,
} from 'lucide-vue-next'
import AgentSearchView from './views/AgentSearchView.vue'
import SimilarSearchView from './views/SimilarSearchView.vue'
import CatalogView from './views/CatalogView.vue'
import FashionMbtiView from './views/FashionMbtiView.vue'
import FavoritesView from './views/FavoritesView.vue'
import PreferencesView from './views/PreferencesView.vue'
import VirtualTryOnView from './views/VirtualTryOnView.vue'
import KnowledgeManagementView from './views/KnowledgeManagementView.vue'
import DebugPipelineView from './views/DebugPipelineView.vue'
import type { AppView, PipelineDebugSession } from './types'
import { useUserLibrary } from './composables/useUserLibrary'
import { useDebugHistory } from './composables/useDebugHistory'

const activeView = ref<AppView>('agent')
const userKey = 'demo-user'
const preferenceRevision = ref(0)
const debugTrace = ref<PipelineDebugSession | null>(null)
const debugHistory = useDebugHistory(userKey)
function updateDebug(trace: PipelineDebugSession) {
  debugTrace.value = trace
  debugHistory.save(trace)
}
const { loadLibrary } = useUserLibrary(userKey)

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
      { id: 'favorites' as const, label: '我的收藏', icon: Bookmark },
      { id: 'preferences' as const, label: '我的偏好', icon: SlidersHorizontal },
    ],
  },
]
const standaloneNav = [
  { id: 'mbti' as const, label: '穿搭測試', icon: Fingerprint },
  { id: 'debug' as const, label: '流程除錯', icon: Bug },
]

const navRef = ref<HTMLElement | null>(null)
const openGroupId = ref<string | null>(null)

function isGroupActive(group: (typeof navGroups)[number]) {
  return group.items.some(item => item.id === activeView.value)
}
function toggleGroup(id: string) {
  openGroupId.value = openGroupId.value === id ? null : id
}
function selectView(id: AppView) {
  activeView.value = id
  openGroupId.value = null
}
function handleDocumentClick(event: MouseEvent) {
  if (openGroupId.value && navRef.value && !navRef.value.contains(event.target as Node)) {
    openGroupId.value = null
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
      <button class="brand" title="Matching Outfit" @click="activeView = 'agent'">
        <span>MO</span>
        <div><strong>Matching Outfit</strong><small>個人穿搭</small></div>
      </button>

      <nav ref="navRef" class="main-navigation" aria-label="主要功能">
        <div v-for="group in navGroups" :key="group.id" class="nav-group">
          <button
            class="nav-top-button nav-group-trigger"
            :class="{ active: isGroupActive(group) }"
            :aria-expanded="openGroupId === group.id"
            @click="toggleGroup(group.id)"
          >
            <component :is="group.icon" :size="17" />{{ group.label }}
            <ChevronDown class="nav-caret" :class="{ open: openGroupId === group.id }" :size="14" />
          </button>
          <div v-if="openGroupId === group.id" class="nav-dropdown">
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

      <button class="user-menu" title="目前登入使用者" @click="activeView = 'preferences'">
        <span>J</span><div><strong>Jenny</strong></div>
      </button>
    </header>

    <div class="app-content">
      <AgentSearchView
        v-show="activeView === 'agent'"
        :user-key="userKey"
        @preference-updated="preferenceRevision++"
        @debug-updated="updateDebug"
      />
      <DebugPipelineView
        v-show="activeView === 'debug'"
        :trace="debugHistory.selected.value ?? debugTrace"
        :history="debugHistory.history.value"
        :selected-id="debugHistory.selectedId.value"
        :storage-error="debugHistory.error.value"
        @select-history="debugHistory.select"
        @show-current="debugHistory.showCurrent"
        @delete-history="debugHistory.remove"
      />
      <KnowledgeManagementView v-if="activeView === 'knowledge'" />
      <SimilarSearchView v-show="activeView === 'similarity'" />
      <CatalogView v-show="activeView === 'catalog'" :user-key="userKey" />
      <FavoritesView v-show="activeView === 'favorites'" :user-key="userKey" />
      <VirtualTryOnView v-if="activeView === 'tryon'" :user-key="userKey" />
      <FashionMbtiView v-if="activeView === 'mbti'" :user-key="userKey" />
      <PreferencesView
        v-show="activeView === 'preferences'"
        :key="preferenceRevision"
        :user-key="userKey"
      />
    </div>

  </div>
</template>
