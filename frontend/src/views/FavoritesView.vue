<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Bookmark, ChevronDown, ChevronUp, ScanFace } from 'lucide-vue-next'
import ProductCard from '../components/ProductCard.vue'
import { useUserLibrary } from '../composables/useUserLibrary'
import { useToast } from '../composables/useToast'
import type {
  FavoriteItem,
  FavoriteOutfit,
  GarmentZone,
  PreferenceType,
  TryOnDraft,
} from '../types'
import { formatCurrency } from '../utils/currency'
import { createTryOnDraft, referenceTypeForCatalogItem } from '../utils/tryOnSelection'

const props = defineProps<{ userKey: string }>()
const emit = defineEmits<{ startTryOn: [draft: TryOnDraft] }>()
const {
  favoriteItems,
  favoriteItemIds,
  favoriteOutfits,
  favoritesLoading,
  outfitPreference,
  loadFavorites,
  setFavoriteItems,
  addOutfitReaction,
  removePreference,
} = useUserLibrary(props.userKey)
const { showError, showSuccess } = useToast()

type FavoriteSort = 'newest' | 'oldest' | 'name' | 'price_asc' | 'price_desc'

const favoriteZoneDefinitions: Array<{
  zone: GarmentZone
  label: string
  eyebrow: string
}> = [
  { zone: 'upper_body', label: '上身', eyebrow: 'Upper body' },
  { zone: 'lower_body', label: '下身', eyebrow: 'Lower body' },
  { zone: 'one_piece', label: '連身穿搭', eyebrow: 'One piece' },
  { zone: 'accessory', label: '配件', eyebrow: 'Accessories' },
  { zone: 'other', label: '其他', eyebrow: 'Other' },
]

const sort = ref<FavoriteSort>('newest')
const actionLoading = ref(false)
const expandedItemIds = ref(new Set<number>())
const pairingIndexByItemId = ref<Record<number, number>>({})

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

const groupedFavorites = computed(() => favoriteZoneDefinitions
  .map((definition) => ({
    ...definition,
    items: sortedFavorites.value.filter(
      (row) => row.item.garment_zone === definition.zone,
    ),
  }))
  .filter((group) => group.items.length > 0))

function pairingsFor(itemId: number): FavoriteOutfit[] {
  return favoriteOutfits.value.filter(
    (outfit) => outfit.items.some((item) => item.id === itemId),
  )
}

function togglePairings(itemId: number) {
  const next = new Set(expandedItemIds.value)
  if (next.has(itemId)) {
    next.delete(itemId)
  } else {
    next.add(itemId)
    pairingIndexByItemId.value = { ...pairingIndexByItemId.value, [itemId]: 0 }
  }
  expandedItemIds.value = next
}

function pairingIndex(itemId: number): number {
  const count = pairingsFor(itemId).length
  return Math.min(pairingIndexByItemId.value[itemId] ?? 0, Math.max(0, count - 1))
}

function selectedPairing(itemId: number): FavoriteOutfit | null {
  return pairingsFor(itemId)[pairingIndex(itemId)] ?? null
}

function movePairing(itemId: number, offset: -1 | 1) {
  const next = pairingIndex(itemId) + offset
  if (next < 0 || next >= pairingsFor(itemId).length) return
  pairingIndexByItemId.value = { ...pairingIndexByItemId.value, [itemId]: next }
}

function tryOnItem(row: FavoriteItem) {
  emit('startTryOn', createTryOnDraft([row.item], 'favorite-item'))
}

function tryOnOutfit(outfit: FavoriteOutfit) {
  emit('startTryOn', createTryOnDraft(outfit.items, 'favorite-outfit', outfit.id))
}

function itemSupportsTryOn(row: FavoriteItem) {
  return referenceTypeForCatalogItem(row.item) !== null
}

function outfitSupportsTryOn(outfit: FavoriteOutfit) {
  return outfit.items.some((item) => referenceTypeForCatalogItem(item) !== null)
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
        ? '偏好已更新，下次規劃穿搭時會避開類似商品'
        : '偏好已更新，下次規劃穿搭時會參考這件商品',
    )
  })
}

async function removeFavorite(itemId: number) {
  await runAction(async () => {
    await setFavoriteItems([itemId], false)
  })
}

onMounted(() => {
  void loadFavorites().catch((reason) => {
    showError(reason instanceof Error ? reason.message : '無法載入收藏')
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

    <div v-if="favoritesLoading" class="loading-state">正在載入收藏…</div>
    <div v-else-if="groupedFavorites.length || favoriteOutfits.length" class="favorites-content">
      <section v-if="favoriteOutfits.length" class="favorite-outfits-section" aria-labelledby="favorite-outfits-title">
        <header class="favorite-group-heading">
          <div>
            <span class="section-kicker">Saved outfits</span>
            <h3 id="favorite-outfits-title">收藏整套</h3>
          </div>
          <span class="favorite-group-count">{{ favoriteOutfits.length }} 套</span>
        </header>
        <div class="favorite-outfit-grid">
          <article v-for="outfit in favoriteOutfits" :key="outfit.id" class="favorite-outfit-card">
            <div class="favorite-outfit-images" :class="{ single: outfit.items.length === 1 }">
              <img
                v-for="item in outfit.items"
                :key="item.id"
                :src="item.image_url"
                :alt="item.product_display_name"
              />
            </div>
            <div class="favorite-outfit-body">
              <div>
                <strong>{{ outfit.items.map((item) => item.product_display_name).join(' ＋ ') }}</strong>
                <small>{{ outfit.items.length }} 件商品</small>
              </div>
              <button
                type="button"
                class="primary-button favorite-tryon-button"
                :disabled="!outfitSupportsTryOn(outfit)"
                :title="outfitSupportsTryOn(outfit) ? '帶入整套商品到虛擬試穿' : '這套商品目前沒有可試穿的品項'"
                @click="tryOnOutfit(outfit)"
              >
                <ScanFace :size="16" />整套試穿
              </button>
            </div>
          </article>
        </div>
      </section>

      <div class="favorite-groups">
      <section
        v-for="group in groupedFavorites"
        :key="group.zone"
        class="favorite-group"
        :aria-labelledby="`favorite-group-${group.zone}`"
      >
        <header class="favorite-group-heading">
          <div>
            <span class="section-kicker">{{ group.eyebrow }}</span>
            <h3 :id="`favorite-group-${group.zone}`">{{ group.label }}</h3>
          </div>
          <span class="favorite-group-count">{{ group.items.length }} 件</span>
        </header>

        <div class="product-grid">
          <ProductCard
            v-for="row in group.items"
            :key="row.item.id"
            :item="row.item"
            :preference-type="outfitPreference([row.item.id])?.preference_type ?? null"
            :favorited="favoriteItemIds.has(row.item.id)"
            :action-loading="actionLoading"
            preference-enabled
            favorite-enabled
            @react="reactToPreference"
            @toggle-favorite="removeFavorite"
          >
            <template #below-media>
              <div
                class="favorite-pairings"
                :class="{ expanded: expandedItemIds.has(row.item.id) }"
              >
                <button
                  type="button"
                  class="favorite-pairings-toggle"
                  :aria-expanded="expandedItemIds.has(row.item.id)"
                  :disabled="pairingsFor(row.item.id).length === 0"
                  @click="pairingsFor(row.item.id).length && togglePairings(row.item.id)"
                >
                  <span>查看搭配({{ pairingsFor(row.item.id).length }})</span>
                  <ChevronDown v-if="expandedItemIds.has(row.item.id)" :size="16" />
                  <ChevronUp v-else-if="pairingsFor(row.item.id).length" :size="16" />
                </button>
                <div
                  v-if="expandedItemIds.has(row.item.id)"
                  class="favorite-pairing-groups"
                >
                  <section
                    v-if="selectedPairing(row.item.id)"
                    :key="selectedPairing(row.item.id)!.id"
                    class="favorite-pairing-group"
                  >
                    <button
                      type="button"
                      class="favorite-pairing-arrow previous"
                      aria-label="查看上一組搭配"
                      :disabled="pairingIndex(row.item.id) === 0"
                      @click="movePairing(row.item.id, -1)"
                    >&lt;</button>
                    <div
                      v-for="partner in selectedPairing(row.item.id)!.items.filter((item) => item.id !== row.item.id)"
                      :key="partner.id"
                      class="favorite-pairing-item"
                    >
                      <img :src="partner.image_url" :alt="partner.product_display_name" />
                      <div>
                        <span>{{ partner.product_display_name }}</span>
                        <small>{{ formatCurrency(partner.price, partner.currency) }}</small>
                      </div>
                    </div>
                    <button
                      type="button"
                      class="favorite-pairing-arrow next"
                      aria-label="查看下一組搭配"
                      :disabled="pairingIndex(row.item.id) === pairingsFor(row.item.id).length - 1"
                      @click="movePairing(row.item.id, 1)"
                    >&gt;</button>
                  </section>
                </div>
              </div>
            </template>
            <button
              type="button"
              class="secondary-button favorite-item-tryon"
              :disabled="!itemSupportsTryOn(row)"
              :title="itemSupportsTryOn(row) ? '帶入這件商品到虛擬試穿' : '目前只支援上身、下身、連身、鞋子與包包'"
              @click="tryOnItem(row)"
            >
              <ScanFace :size="15" />{{ itemSupportsTryOn(row) ? '試穿這件' : '目前不支援試穿' }}
            </button>
          </ProductCard>
        </div>
      </section>
      </div>
    </div>
    <div v-else class="empty-view">
      <Bookmark :size="34" />
      <h3>尚未收藏任何商品</h3>
    </div>
  </section>
</template>
