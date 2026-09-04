<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Bookmark, Bug, MessageSquareText, ScanFace, Search, Shirt, SlidersHorizontal, X } from 'lucide-vue-next'
import AgentSearchView from './views/AgentSearchView.vue'
import SimilarSearchView from './views/SimilarSearchView.vue'
import CatalogView from './views/CatalogView.vue'
import FavoritesView from './views/FavoritesView.vue'
import PreferencesView from './views/PreferencesView.vue'
import VirtualTryOnView from './views/VirtualTryOnView.vue'
import KnowledgeManagementView from './views/KnowledgeManagementView.vue'
import DebugPipelineView from './views/DebugPipelineView.vue'
import type { AppView, PipelineDebugSession } from './types'
import { useUserLibrary } from './composables/useUserLibrary'

const activeView = ref<AppView>('agent')
const knowledgeOpen = ref(false)
const userKey = 'demo-user'
const preferenceRevision = ref(0)
const debugTrace = ref<PipelineDebugSession | null>(null)
const { loadLibrary } = useUserLibrary(userKey)

const navigation = [
  { id: 'agent' as const, label: '找搭配', icon: MessageSquareText },
  { id: 'debug' as const, label: '流程除錯', icon: Bug },
  { id: 'similarity' as const, label: '找相似', icon: Search },
  { id: 'catalog' as const, label: '衣服商品', icon: Shirt },
  { id: 'favorites' as const, label: '我的收藏', icon: Bookmark },
  { id: 'tryon' as const, label: '虛擬試穿', icon: ScanFace },
  { id: 'preferences' as const, label: '我的偏好', icon: SlidersHorizontal },
]

function closeKnowledgeOnEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') knowledgeOpen.value = false
}

onMounted(() => {
  window.addEventListener('keydown', closeKnowledgeOnEscape)
  void loadLibrary().catch(() => undefined)
})
onBeforeUnmount(() => window.removeEventListener('keydown', closeKnowledgeOnEscape))
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <button class="brand" title="Matching Outfit" @click="activeView = 'agent'">
        <span>MO</span>
        <div><strong>Matching Outfit</strong><small>Styling workspace</small></div>
      </button>

      <nav class="main-navigation" aria-label="主要功能">
        <button
          v-for="item in navigation"
          :key="item.id"
          :class="{ active: activeView === item.id }"
          @click="activeView = item.id"
        >
          <component :is="item.icon" :size="17" />{{ item.label }}
        </button>
      </nav>

      <button class="user-menu" title="目前登入使用者" @click="activeView = 'preferences'">
        <span>J</span><div><strong>Jenny</strong><small>{{ userKey }}</small></div>
      </button>
    </header>

    <div class="app-content">
      <AgentSearchView
        v-show="activeView === 'agent'"
        :user-key="userKey"
        @preference-updated="preferenceRevision++"
        @open-knowledge="knowledgeOpen = true"
        @debug-updated="debugTrace = $event"
      />
      <DebugPipelineView v-show="activeView === 'debug'" :trace="debugTrace" />
      <SimilarSearchView v-show="activeView === 'similarity'" />
      <CatalogView v-show="activeView === 'catalog'" :user-key="userKey" />
      <FavoritesView v-show="activeView === 'favorites'" :user-key="userKey" />
      <VirtualTryOnView v-if="activeView === 'tryon'" :user-key="userKey" />
      <PreferencesView
        v-show="activeView === 'preferences'"
        :key="preferenceRevision"
        :user-key="userKey"
      />
    </div>

    <Teleport to="body">
      <div v-if="knowledgeOpen" class="knowledge-modal-backdrop" @click.self="knowledgeOpen = false">
        <section class="knowledge-modal-panel" role="dialog" aria-modal="true" aria-label="文章與搭配知識">
          <button class="knowledge-modal-close" title="關閉知識來源" @click="knowledgeOpen = false">
            <X :size="20" />
          </button>
          <KnowledgeManagementView />
        </section>
      </div>
    </Teleport>
  </div>
</template>
