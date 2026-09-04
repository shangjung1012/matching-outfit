<script setup lang="ts">
import { Heart } from 'lucide-vue-next'
import type { CatalogItem, ClothResult } from '../types'

defineProps<{
  item: CatalogItem | ClothResult
  liked?: boolean
  likeable?: boolean
  showSimilarity?: boolean
}>()

defineEmits<{ toggleLike: [id: number] }>()
</script>

<template>
  <article class="product-card">
    <div class="product-media">
      <img :src="item.image_url" :alt="item.product_display_name" />
      <span class="zone-badge">{{ item.garment_zone.replace('_', ' ') }}</span>
      <button
        v-if="likeable"
        class="heart-button"
        :class="{ active: liked }"
        :title="liked ? '取消喜歡' : '喜歡這件商品'"
        @click="$emit('toggleLike', item.id)"
      >
        <Heart :size="18" :fill="liked ? 'currentColor' : 'none'" />
      </button>
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
        <strong>NT$ {{ item.price.toLocaleString() }}</strong>
        <span v-if="showSimilarity && 'similarity' in item">{{ Math.round(item.similarity * 100) }}% match</span>
      </div>
    </div>
  </article>
</template>
