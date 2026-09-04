<script setup lang="ts">
import { computed } from 'vue'
import { Bookmark, ChevronDown, ExternalLink, Heart, Sparkles } from 'lucide-vue-next'
import type { OutfitRecommendation, QueryDraft, StylingGuide } from '../types'
import { formatCurrency } from '../utils/currency'

const props = defineProps<{
  outfit: OutfitRecommendation
  rank: number
  preferred: boolean
  favorited: boolean
  actionLoading?: boolean
  featured?: boolean
  userRequest?: string
  stylingGuide?: StylingGuide | null
  queries?: QueryDraft[]
}>()

defineEmits<{ togglePreference: []; toggleFavorite: [] }>()

const zoneLabels = {
  upper_body: '上身',
  lower_body: '下身',
  one_piece: '單件套裝',
  accessory: '配件',
  other: '單品',
} as const

const planningReasons = computed(() => {
  const zones = new Set(props.outfit.items.map((item) => item.garment_zone))
  return Array.from(new Set(
    (props.queries || [])
      .filter((query) => query.selected && zones.has(query.garment_zone))
      .map((query) => query.rationale.trim())
      .filter(Boolean),
  )).slice(0, props.outfit.kind === 'separates' ? 4 : 2)
})

function itemSelectionReason(item: OutfitRecommendation['items'][number]): string {
  const identity = [item.base_colour, item.article_type]
    .filter((value): value is string => Boolean(value?.trim()))
    .join(' ')
  const similarity = Math.round(item.similarity * 100)
  return `${zoneLabels[item.garment_zone]}選擇「${item.product_display_name}」：${identity || '商品外觀'}在該區域的搜尋方向中相似度為 ${similarity}%。`
}
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
      <details class="outfit-explanation">
        <summary>
          <span><Sparkles :size="14" />為什麼這樣搭？</span>
          <ChevronDown :size="15" class="explanation-chevron" />
        </summary>
        <div class="outfit-explanation-content">
          <section v-if="userRequest">
            <strong>你說了什麼</strong>
            <p>「{{ userRequest }}」</p>
          </section>
          <section v-if="stylingGuide?.concept || planningReasons.length">
            <strong>所以怎麼理解</strong>
            <p v-if="stylingGuide?.concept">{{ stylingGuide.concept }}</p>
            <ul v-if="planningReasons.length">
              <li v-for="reason in planningReasons" :key="reason">{{ reason }}</li>
            </ul>
          </section>
          <section>
            <strong>因此選擇了什麼</strong>
            <ul>
              <li v-for="item in outfit.items" :key="`${item.id}-explanation`">
                {{ itemSelectionReason(item) }}
              </li>
            </ul>
            <p v-if="outfit.score_breakdown">
              組合後的搭配協調度為 {{ Math.round(outfit.score_breakdown.compatibility * 100) }}%，
              場合符合度為 {{ Math.round(outfit.score_breakdown.context_fit * 100) }}%。
            </p>
          </section>
          <section v-if="outfit.aesthetic_review">
            <strong>最後怎麼確認</strong>
            <p>
              視覺審查再檢查場合、配色、輪廓和材質，給出的整體美感為
              {{ outfit.aesthetic_review.overall_aesthetic }} 分。{{ outfit.aesthetic_review.reason }}
            </p>
          </section>
          <section v-else>
            <strong>最後怎麼確認</strong>
            <p>目前由商品相似度、搭配協調度與場合符合度共同排序；本次沒有使用視覺美感審查。</p>
          </section>
        </div>
      </details>
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
