<script setup lang="ts">
import { Bookmark, Heart } from 'lucide-vue-next'
import type { CatalogItem, ClothResult } from '../types'
import { formatCurrency } from '../utils/currency'

defineProps<{
  item: CatalogItem | ClothResult
  preferred?: boolean
  preferenceEnabled?: boolean
  favorited?: boolean
  favoriteEnabled?: boolean
  actionLoading?: boolean
  showSimilarity?: boolean
}>()

defineEmits<{
  togglePreference: [id: number]
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
          :class="{ active: preferred }"
          :disabled="actionLoading"
          :title="preferred ? '停用這件商品的偏好' : '將這件商品加入偏好'"
          @click="$emit('togglePreference', item.id)"
        >
          <Heart :size="18" :fill="preferred ? 'currentColor' : 'none'" />
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
