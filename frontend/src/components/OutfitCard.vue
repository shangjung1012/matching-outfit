<script setup lang="ts">
import { Heart, Sparkles } from 'lucide-vue-next'
import type { OutfitRecommendation } from '../types'

defineProps<{
  outfit: OutfitRecommendation
  rank: number
  likedIds: Set<number>
  featured?: boolean
}>()

defineEmits<{ toggleLike: [id: number] }>()
</script>

<template>
  <article class="recommendation-card" :class="{ featured }">
    <div class="recommendation-visual" :class="{ single: outfit.items.length === 1 }">
      <div v-for="item in outfit.items" :key="item.id" class="recommendation-item">
        <img :src="item.image_url" :alt="item.product_display_name" />
        <button
          class="heart-button"
          :class="{ active: likedIds.has(item.id) }"
          :title="likedIds.has(item.id) ? '取消喜歡' : '喜歡這件商品'"
          @click="$emit('toggleLike', item.id)"
        >
          <Heart :size="18" :fill="likedIds.has(item.id) ? 'currentColor' : 'none'" />
        </button>
      </div>
    </div>
    <div class="recommendation-body">
      <div class="recommendation-rank">
        <span>#{{ rank }}</span>
        <strong>{{ Math.round(outfit.score * 100) }}% match</strong>
      </div>
      <div class="recommendation-kind">
        <Sparkles :size="15" />
        {{ outfit.kind === 'separates' ? '上下身搭配' : '單件套裝' }}
      </div>
      <h3>{{ outfit.items.map((item) => item.product_display_name).join(' + ') }}</h3>
      <div class="recommendation-tags">
        <span v-for="item in outfit.items" :key="`${item.id}-tag`">
          {{ item.base_colour }} {{ item.article_type }}
        </span>
      </div>
      <div class="recommendation-footer">
        <strong>NT$ {{ outfit.items.reduce((sum, item) => sum + item.price, 0).toLocaleString() }}</strong>
        <span>{{ outfit.items.length }} 件商品</span>
      </div>
    </div>
  </article>
</template>
