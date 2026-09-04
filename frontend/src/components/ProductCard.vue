<script setup lang="ts">
import { Bookmark, ThumbsDown, ThumbsUp } from 'lucide-vue-next'
import type { CatalogItem, ClothResult, PreferenceType } from '../types'
import { formatCurrency } from '../utils/currency'

defineProps<{
  item: CatalogItem | ClothResult
  preferenceType?: PreferenceType | null
  preferenceEnabled?: boolean
  favorited?: boolean
  favoriteEnabled?: boolean
  actionLoading?: boolean
  showSimilarity?: boolean
}>()

defineEmits<{
  react: [id: number, type: PreferenceType]
  toggleFavorite: [id: number]
}>()
</script>

<template>
  <article class="product-card">
    <div class="product-media">
      <img :src="item.image_url" :alt="item.product_display_name" />
      <span class="zone-badge">{{ item.garment_zone.replace('_', ' ') }}</span>
      <div v-if="preferenceEnabled || favoriteEnabled" class="product-card-actions">
        <button
          v-if="preferenceEnabled"
          class="product-action-button preference"
          :class="{ active: preferenceType === 'prefer' }"
          :disabled="actionLoading"
          :title="preferenceType === 'prefer' ? '取消喜歡這件商品' : '喜歡這件商品'"
          @click="$emit('react', item.id, 'prefer')"
        >
          <ThumbsUp :size="18" :fill="preferenceType === 'prefer' ? 'currentColor' : 'none'" />
        </button>
        <button
          v-if="preferenceEnabled"
          class="product-action-button preference avoid"
          :class="{ active: preferenceType === 'avoid' }"
          :disabled="actionLoading"
          :title="preferenceType === 'avoid' ? '取消不喜歡這件商品' : '不喜歡這件商品'"
          @click="$emit('react', item.id, 'avoid')"
        >
          <ThumbsDown :size="18" :fill="preferenceType === 'avoid' ? 'currentColor' : 'none'" />
        </button>
        <button
          v-if="favoriteEnabled"
          class="product-action-button favorite"
          :class="{ active: favorited }"
          :disabled="actionLoading"
          :title="favorited ? '取消收藏這件商品' : '收藏這件商品'"
          @click="$emit('toggleFavorite', item.id)"
        >
          <Bookmark :size="18" :fill="favorited ? 'currentColor' : 'none'" />
        </button>
      </div>
    </div>
    <div class="product-body">
      <div class="product-meta">
        <span>{{ item.article_type || 'Clothing' }}</span>
        <span v-if="item.base_colour" class="color-meta">
          <i :style="{ backgroundColor: item.base_colour }" />{{ item.base_colour }}
        </span>
      </div>
      <h3>{{ item.product_display_name }}</h3>
      <div class="product-footer">
        <strong>{{ formatCurrency(item.price, item.currency) }}</strong>
        <span v-if="showSimilarity && 'similarity' in item">{{ Math.round(item.similarity * 100) }}% match</span>
      </div>
      <slot />
    </div>
  </article>
</template>
