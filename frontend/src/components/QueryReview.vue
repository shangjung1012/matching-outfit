<script setup lang="ts">
import { computed } from 'vue'
import { Check, RotateCcw, X } from 'lucide-vue-next'
import type { QueryDraft } from '../types'

const props = defineProps<{ queries: QueryDraft[]; loading: boolean }>()
const emit = defineEmits<{
  select: [id: string, selected: boolean]
  search: []
}>()

const active = computed(() => props.queries.filter((query) => query.selected))
const removed = computed(() => props.queries.filter((query) => !query.selected))
const zoneLabels: Record<QueryDraft['garment_zone'], string> = {
  upper_body: '上半身',
  lower_body: '下半身',
  one_piece: '連身穿搭',
  accessory: '配件',
  other: '其他',
}
</script>

<template>
  <section class="query-review">
    <header class="view-heading compact-heading">
      <div>
        <span class="section-kicker">Styling directions</span>
        <h2>選擇搭配方向</h2>
      </div>
      <span class="count-badge">已選擇 {{ active.length }} 項</span>
    </header>

    <div class="query-stack">
      <article v-for="query in active" :key="query.id" class="query-item">
        <span class="query-zone">{{ zoneLabels[query.garment_zone] }}</span>
        <div class="query-copy">
          <strong>{{ query.rationale }}</strong>
        </div>
        <button class="icon-button" title="移除搭配方向" :disabled="loading" @click="$emit('select', query.id, false)">
          <X :size="18" />
        </button>
      </article>
    </div>

    <div v-if="removed.length" class="removed-queries">
      <span>已移除</span>
      <button v-for="query in removed" :key="query.id" :disabled="loading" @click="$emit('select', query.id, true)">
        <RotateCcw :size="14" />{{ zoneLabels[query.garment_zone] }}
      </button>
    </div>

    <button class="primary-button query-search-button" :disabled="loading || !active.length" @click="$emit('search')">
      <Check :size="18" />{{ loading ? '搜尋中…' : '開始找搭配' }}
    </button>
  </section>
</template>
