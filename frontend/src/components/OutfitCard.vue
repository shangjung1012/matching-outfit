<script setup lang="ts">
import { computed } from 'vue'
import { Bookmark, ChevronDown, ExternalLink, Sparkles, ThumbsDown, ThumbsUp } from 'lucide-vue-next'
import type { OutfitRecommendation, PreferenceType, QueryDraft, StylingGuide } from '../types'
import { formatCurrency } from '../utils/currency'

const props = defineProps<{
  outfit: OutfitRecommendation
  preferenceType: PreferenceType | null
  favorited: boolean
  actionLoading?: boolean
  userRequest?: string
  stylingGuide?: StylingGuide | null
  queries?: QueryDraft[]
  referencePreviewUrl?: string
}>()

defineEmits<{ react: [type: PreferenceType]; toggleFavorite: [] }>()

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
      .filter((query) => (
        query.selected
        && zones.has(query.garment_zone)
        && query.direction_id === props.outfit.direction_id
      ))
      .map((query) => query.rationale.trim())
      .filter(Boolean),
  )).slice(0, props.outfit.kind === 'separates' ? 2 : 1)
})

const upperItem = computed(() => props.outfit.items.find((item) => item.garment_zone === 'upper_body'))
const lowerItem = computed(() => props.outfit.items.find((item) => item.garment_zone === 'lower_body'))
const onePieceItem = computed(() => props.outfit.items.find((item) => item.garment_zone === 'one_piece'))
const shoeItem = computed(() => props.outfit.items.find((item) => item.garment_zone === 'accessory'))

function visibleItemDescription(item: OutfitRecommendation['items'][number]): string {
  const traits = [item.base_colour, item.article_type]
    .filter((value): value is string => Boolean(value?.trim()))
    .join(' ')
  return `「${item.product_display_name}」${traits ? `（${traits}）` : ''}`
}

function itemSelectionReason(item: OutfitRecommendation['items'][number]): string {
  const identity = [item.base_colour, item.article_type]
    .filter((value): value is string => Boolean(value?.trim()))
    .join(' ')
  const similarity = Math.round(item.similarity * 100)
  return `${zoneLabels[item.garment_zone]}選擇「${item.product_display_name}」：${identity || '商品外觀'}在該區域的搜尋方向中相似度為 ${similarity}%。`
}
</script>

<template>
  <article class="recommendation-card">
    <div class="recommendation-visual" :class="{ single: outfit.items.length === 1 }">
      <div v-for="item in outfit.items" :key="item.id" class="recommendation-item">
        <a :href="item.is_reference ? (referencePreviewUrl || '#') : item.image_url" target="_blank" rel="noopener noreferrer" :aria-label="`查看 ${item.product_display_name} 原始商品圖片`">
          <img :src="item.is_reference ? referencePreviewUrl : item.image_url" :alt="item.product_display_name" />
          <span class="outfit-original-image"><ExternalLink :size="12" />{{ item.is_reference ? '你的單品' : '查看原圖' }}</span>
        </a>
      </div>
    </div>
    <div class="recommendation-body">
      <div class="recommendation-rank">
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
      <div v-if="outfit.aesthetic_review" class="outfit-review-summary">
        <p v-if="upperItem"><strong>上衣：</strong>{{ visibleItemDescription(upperItem) }}</p>
        <p v-if="lowerItem"><strong>下身：</strong>{{ visibleItemDescription(lowerItem) }}</p>
        <p v-if="onePieceItem"><strong>洋裝／連身：</strong>{{ visibleItemDescription(onePieceItem) }}</p>
        <p v-if="shoeItem"><strong>鞋子：</strong>{{ visibleItemDescription(shoeItem) }}</p>
        <p><strong>搭配與整體：</strong>{{ outfit.aesthetic_review.reason }}</p>
      </div>
      <aside v-if="outfit.aesthetic_review?.inner_layer_suggestion" class="outfit-inner-layer">
        <strong>內搭建議</strong>
        <p>{{ outfit.aesthetic_review.inner_layer_suggestion }}</p>
        <small>穿搭建議，非本次推薦商品；不含於顯示價格。</small>
      </aside>
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
              {{ outfit.aesthetic_review.overall_aesthetic }} 分。
            </p>
          </section>
          <section v-else>
            <strong>最後怎麼確認</strong>
            <p>這套沒有圖片美感審查結果，目前僅有初步搭配分數，請勿把它視為已通過美感審查。</p>
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
            :class="{ active: preferenceType === 'prefer' }"
            :disabled="actionLoading"
            :title="preferenceType === 'prefer' ? '取消喜歡這套搭配' : '喜歡這套搭配'"
            @click="$emit('react', 'prefer')"
          >
            <ThumbsUp :size="17" :fill="preferenceType === 'prefer' ? 'currentColor' : 'none'" />
          </button>
          <button
            class="outfit-action-button preference avoid"
            :class="{ active: preferenceType === 'avoid' }"
            :disabled="actionLoading"
            :title="preferenceType === 'avoid' ? '取消不喜歡這套搭配' : '不喜歡這套搭配'"
            @click="$emit('react', 'avoid')"
          >
            <ThumbsDown :size="17" :fill="preferenceType === 'avoid' ? 'currentColor' : 'none'" />
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
