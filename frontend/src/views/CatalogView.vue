<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Search, Shirt } from 'lucide-vue-next'
import { getCatalog, searchCatalogByEmbedding } from '../api'
import ProductCard from '../components/ProductCard.vue'
import { useUserLibrary } from '../composables/useUserLibrary'
import { useToast } from '../composables/useToast'
import type { CatalogItem, ClothResult, PreferenceType } from '../types'

const props = defineProps<{ userKey: string }>()
const {
  favoriteItemIds,
  outfitPreference,
  setFavoriteItems,
  addOutfitReaction,
  removePreference,
} = useUserLibrary(props.userKey)
const { showError, showSuccess } = useToast()

const items = ref<Array<CatalogItem | ClothResult>>([])
const total = ref(0)
const zone = ref('')
const search = ref('')
const semanticSearchActive = ref(false)
const loading = ref(false)
const actionLoading = ref(false)

const zones = [
  { value: '', label: '全部' },
  { value: 'upper_body', label: '上半身' },
  { value: 'lower_body', label: '下半身' },
  { value: 'one_piece', label: '單件套裝' },
  { value: 'accessory', label: '配件' },
]

async function loadCatalog() {
  loading.value = true
  try {
    const query = search.value.trim()
    const response = query
      ? await searchCatalogByEmbedding(query, props.userKey, zone.value)
      : await getCatalog(zone.value)
    items.value = response.items
    total.value = response.total
    semanticSearchActive.value = Boolean(query)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '無法載入商品')
  } finally {
    loading.value = false
  }
}

async function runAction(task: () => Promise<void>) {
  actionLoading.value = true
  try {
    await task()
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '操作失敗')
  } finally {
    actionLoading.value = false
  }
}

async function reactToPreference(itemId: number, preferenceType: PreferenceType) {
  await runAction(async () => {
    const current = outfitPreference([itemId])
    if (current?.preference_type === preferenceType) {
      await removePreference(current.id)
      showSuccess('這件商品的偏好已移除。')
      return
    }
    if (current) await removePreference(current.id)
    await addOutfitReaction([itemId], '', null, preferenceType)
    showSuccess(
      preferenceType === 'avoid'
        ? '已記錄不喜歡這件商品，下次規劃穿搭時會避開它。'
        : '偏好已更新，下次規劃穿搭時會參考這件商品。',
    )
  })
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

    <div v-if="loading" class="loading-state">正在載入商品…</div>
    <div v-else-if="items.length" class="product-grid">
      <ProductCard
        v-for="item in items"
        :key="item.id"
        :item="item"
        :preference-type="outfitPreference([item.id])?.preference_type ?? null"
        :favorited="favoriteItemIds.has(item.id)"
        :action-loading="actionLoading"
        preference-enabled
        favorite-enabled
        :show-similarity="semanticSearchActive"
        @react="reactToPreference"
        @toggle-favorite="toggleFavorite"
      />
    </div>
    <div v-else class="empty-view">
      <Shirt :size="32" />
      <h3>沒有符合條件的商品</h3>
    </div>
  </section>
</template>
