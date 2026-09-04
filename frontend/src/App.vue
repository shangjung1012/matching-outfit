<script setup lang="ts">
import { ref } from 'vue'
import { MessageSquareText, Shirt, SlidersHorizontal } from 'lucide-vue-next'
import AgentSearchView from './views/AgentSearchView.vue'
import CatalogView from './views/CatalogView.vue'
import PreferencesView from './views/PreferencesView.vue'
import type { AppView } from './types'

const activeView = ref<AppView>('agent')
const userKey = 'demo-user'
const preferenceRevision = ref(0)

const navigation = [
  { id: 'agent' as const, label: 'Agent 搜尋', icon: MessageSquareText },
  { id: 'catalog' as const, label: '衣服商品', icon: Shirt },
  { id: 'preferences' as const, label: '我的偏好', icon: SlidersHorizontal },
]
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
      />
      <CatalogView v-show="activeView === 'catalog'" />
      <PreferencesView
        v-show="activeView === 'preferences'"
        :key="preferenceRevision"
        :user-key="userKey"
      />
    </div>
  </div>
</template>
