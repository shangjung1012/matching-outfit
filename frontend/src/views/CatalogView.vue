<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Check, Search, Shirt } from 'lucide-vue-next'
import { getCatalog, proposeSoftFromItem, searchCatalogByEmbedding } from '../api'
import ProductCard from '../components/ProductCard.vue'
import PreferenceProposalPanel from '../components/PreferenceProposalPanel.vue'
import { useUserLibrary } from '../composables/useUserLibrary'
import type { CatalogItem, ClothResult, StylePreferenceProposal } from '../types'

const props = defineProps<{ userKey: string }>()
const {
  favoriteItemIds,
  isPreferred,
  setFavoriteItems,
  confirmPreferences,
  deactivatePreferenceOrigin,
} = useUserLibrary(props.userKey)

const items = ref<Array<CatalogItem | ClothResult>>([])
const total = ref(0)
const zone = ref('')
const search = ref('')
const semanticSearchActive = ref(false)
const loading = ref(false)
const actionLoading = ref(false)
const error = ref('')
const proposal = ref<StylePreferenceProposal | null>(null)
const preferenceStatus = ref('')

const zones = [
  { value: '', label: '全部' },
  { value: 'upper_body', label: '上半身' },
  { value: 'lower_body', label: '下半身' },
  { value: 'one_piece', label: '單件套裝' },
  { value: 'accessory', label: '配件' },
]

async function loadCatalog() {
  loading.value = true
  error.value = ''
  try {
    const query = search.value.trim()
    const response = query
      ? await searchCatalogByEmbedding(query, props.userKey, zone.value)
      : await getCatalog(zone.value)
    items.value = response.items
    total.value = response.total
    semanticSearchActive.value = Boolean(query)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '無法載入商品'
  } finally {
    loading.value = false
  }
}

async function runAction(task: () => Promise<void>) {
  actionLoading.value = true
  error.value = ''
  try {
    await task()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '操作失敗'
  } finally {
    actionLoading.value = false
  }
}

async function togglePreference(itemId: number) {
  await runAction(async () => {
    preferenceStatus.value = ''
    if (isPreferred([itemId])) {
      await deactivatePreferenceOrigin([itemId])
      proposal.value = null
      preferenceStatus.value = '這件商品的偏好已停用，可在「我的偏好」重新啟用。'
      return
    }
    proposal.value = await proposeSoftFromItem(props.userKey, itemId)
  })
}

async function confirmProposal() {
  if (!proposal.value) return
  await runAction(async () => {
    await confirmPreferences(proposal.value!.proposals)
    proposal.value = null
    preferenceStatus.value = '偏好已更新，下次規劃穿搭時會參考這件商品。'
  })
}

function dismissProposal() {
  proposal.value = null
}

async function toggleFavorite(itemId: number) {
  await runAction(async () => {
    await setFavoriteItems([itemId], !favoriteItemIds.value.has(itemId))
  })
}

onMounted(loadCatalog)
</script>

<template>
  <section class="page-view catalog-view">
    <header class="view-heading">
      <div>
        <span class="section-kicker">Catalog</span>
        <h2>衣服商品</h2>
        <p>{{ semanticSearchActive ? `${total} 件相似商品` : `${total} 件已匯入商品` }}</p>
      </div>
      <div class="catalog-search">
        <Search :size="17" />
        <input v-model="search" placeholder="lightweight white summer dress" @keyup.enter="loadCatalog" />
      </div>
    </header>

    <div class="filter-toolbar">
      <div class="segmented-control" aria-label="商品分類">
        <button
          v-for="option in zones"
          :key="option.value"
          :class="{ active: zone === option.value }"
          @click="zone = option.value; loadCatalog()"
        >
          {{ option.label }}
        </button>
      </div>
      <button class="secondary-button" :disabled="loading" @click="loadCatalog"><Search :size="16" />搜尋</button>
    </div>

    <p v-if="error" class="error-banner">{{ error }}</p>
    <div v-if="proposal || preferenceStatus" class="preference-confirmation-area">
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
    <div v-if="loading" class="loading-state">正在載入商品…</div>
    <div v-else-if="items.length" class="product-grid">
      <ProductCard
        v-for="item in items"
        :key="item.id"
        :item="item"
        :preferred="isPreferred([item.id])"
        :favorited="favoriteItemIds.has(item.id)"
        :action-loading="actionLoading"
        preference-enabled
        favorite-enabled
        :show-similarity="semanticSearchActive"
        @toggle-preference="togglePreference"
        @toggle-favorite="toggleFavorite"
      />
    </div>
    <div v-else class="empty-view">
      <Shirt :size="32" />
      <h3>沒有符合條件的商品</h3>
    </div>
  </section>
</template>
