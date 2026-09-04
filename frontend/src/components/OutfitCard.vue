<script setup lang="ts">
import { Bookmark, ExternalLink, Heart, Sparkles } from 'lucide-vue-next'
import type { OutfitRecommendation } from '../types'
import { formatCurrency } from '../utils/currency'

defineProps<{
  outfit: OutfitRecommendation
  rank: number
  preferred: boolean
  favorited: boolean
  actionLoading?: boolean
  featured?: boolean
}>()

defineEmits<{ togglePreference: []; toggleFavorite: [] }>()
</script>

<template>
  <article class="recommendation-card" :class="{ featured }">
    <div class="recommendation-visual" :class="{ single: outfit.items.length === 1 }">
      <div v-for="item in outfit.items" :key="item.id" class="recommendation-item">
        <img :src="item.image_url" :alt="item.product_display_name" />
      </div>
    </div>
    <div class="recommendation-body">
      <div class="recommendation-rank">
        <span>#{{ rank }}</span>
        <strong>{{ Math.round(outfit.score * 100) }}% match</strong>
        <strong v-if="outfit.aesthetic_review">
          美感 {{ outfit.aesthetic_review.overall_aesthetic }}
        </strong>
      </div>
      <div class="recommendation-kind">
        <Sparkles :size="15" />
        {{ outfit.kind === 'separates' ? '上下身搭配' : '單件套裝' }}
      </div>
      <h3>{{ outfit.items.map((item) => item.product_display_name).join(' + ') }}</h3>
      <p v-if="outfit.aesthetic_review">{{ outfit.aesthetic_review.reason }}</p>
      <div class="recommendation-tags">
        <span v-for="item in outfit.items" :key="`${item.id}-tag`">
          {{ item.base_colour }} {{ item.article_type }}
        </span>
      </div>
      <div class="recommendation-footer">
        <strong>
          {{
            formatCurrency(
              outfit.items.reduce((sum, item) => sum + item.price, 0),
              outfit.items[0]?.currency,
            )
          }}
        </strong>
        <span>{{ outfit.items.length }} 件商品</span>
        <div class="outfit-card-actions">
          <button
            class="outfit-action-button preference"
            :class="{ active: preferred }"
            :disabled="actionLoading"
            :title="preferred ? '停用這套搭配的偏好' : '將這套搭配加入偏好'"
            @click="$emit('togglePreference')"
          >
            <Heart :size="17" :fill="preferred ? 'currentColor' : 'none'" />
          </button>
          <button
            class="outfit-action-button favorite"
            :class="{ active: favorited }"
            :disabled="actionLoading"
            :title="favorited ? '取消收藏整套商品' : '收藏整套商品'"
            @click="$emit('toggleFavorite')"
          >
            <Bookmark :size="17" :fill="favorited ? 'currentColor' : 'none'" />
          </button>
        </div>
      </div>
    </div>
    <div v-if="outfit.references.length" class="recommendation-references">
      <div class="recommendation-reference-title">
        <ExternalLink :size="14" />
        <strong>參考來源</strong>
      </div>
      <ul>
        <li v-for="reference in outfit.references" :key="reference.url">
          <a :href="reference.url" target="_blank" rel="noopener noreferrer">
            {{ reference.title }}
          </a>
        </li>
      </ul>
    </div>
  </article>
</template>
