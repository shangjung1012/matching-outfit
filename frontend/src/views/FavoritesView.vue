<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Bookmark, Check } from 'lucide-vue-next'
import { proposeSoftFromItem } from '../api'
import PreferenceProposalPanel from '../components/PreferenceProposalPanel.vue'
import ProductCard from '../components/ProductCard.vue'
import { useUserLibrary } from '../composables/useUserLibrary'
import type { FavoriteItem, StylePreferenceProposal } from '../types'

const props = defineProps<{ userKey: string }>()
const {
  favoriteItems,
  favoriteItemIds,
  favoritesLoading,
  isPreferred,
  loadFavorites,
  setFavoriteItems,
  confirmPreferences,
  deactivatePreferenceOrigin,
} = useUserLibrary(props.userKey)

type FavoriteSort = 'newest' | 'oldest' | 'name' | 'price_asc' | 'price_desc'

const sort = ref<FavoriteSort>('newest')
const actionLoading = ref(false)
const error = ref('')
const proposal = ref<StylePreferenceProposal | null>(null)
const preferenceStatus = ref('')

const sortedFavorites = computed(() => {
  const rows = [...favoriteItems.value]
  const byDate = (row: FavoriteItem) => new Date(row.favorited_at).getTime()
  if (sort.value === 'oldest') return rows.sort((left, right) => byDate(left) - byDate(right))
  if (sort.value === 'name') {
    return rows.sort((left, right) => (
      left.item.product_display_name.localeCompare(right.item.product_display_name, 'zh-Hant')
    ))
  }
  if (sort.value === 'price_asc') {
    return rows.sort((left, right) => left.item.price - right.item.price)
  }
  if (sort.value === 'price_desc') {
    return rows.sort((left, right) => right.item.price - left.item.price)
  }
  return rows.sort((left, right) => byDate(right) - byDate(left))
})

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

async function removeFavorite(itemId: number) {
  await runAction(async () => {
    await setFavoriteItems([itemId], false)
  })
}

onMounted(() => {
  void loadFavorites().catch((reason) => {
    error.value = reason instanceof Error ? reason.message : '無法載入收藏'
  })
})
</script>

<template>
  <section class="page-view favorites-view">
    <header class="view-heading favorites-heading">
      <div>
        <span class="section-kicker">Favorites</span>
        <h2>我的收藏</h2>
        <p>{{ favoriteItems.length }} 件收藏商品</p>
      </div>
      <label class="favorites-sort">
        <span>排序</span>
        <select v-model="sort">
          <option value="newest">最新收藏</option>
          <option value="oldest">最早收藏</option>
          <option value="name">商品名稱</option>
          <option value="price_asc">價格低到高</option>
          <option value="price_desc">價格高到低</option>
        </select>
      </label>
    </header>

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

    <div v-if="favoritesLoading" class="loading-state">正在載入收藏…</div>
    <div v-else-if="sortedFavorites.length" class="product-grid">
      <ProductCard
        v-for="row in sortedFavorites"
        :key="row.item.id"
        :item="row.item"
        :preferred="isPreferred([row.item.id])"
        :favorited="favoriteItemIds.has(row.item.id)"
        :action-loading="actionLoading"
        preference-enabled
        favorite-enabled
        @toggle-preference="togglePreference"
        @toggle-favorite="removeFavorite"
      />
    </div>
    <div v-else class="empty-view">
      <Bookmark :size="34" />
      <h3>尚未收藏任何商品</h3>
      <p>在商品或推薦穿搭上按下書籤，就會顯示在這裡。</p>
    </div>
  </section>
</template>
