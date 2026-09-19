<script setup lang="ts">
import { computed } from 'vue'
import { Check, RotateCcw, X } from 'lucide-vue-next'
import type { QueryDraft } from '../types'

const props = defineProps<{ queries: QueryDraft[]; loading: boolean }>()
const emit = defineEmits<{
  select: [ids: string[], selected: boolean]
  search: []
}>()

type DirectionGroup = {
  id: string
  queries: QueryDraft[]
  selected: boolean
  separates: boolean
}

const directionGroups = computed<DirectionGroup[]>(() => {
  const groups = new Map<string, { id: string; queries: QueryDraft[] }>()
  for (const query of props.queries) {
    const id = query.direction_id?.trim() || query.id
    const group = groups.get(id) ?? { id, queries: [] }
    group.queries.push(query)
    groups.set(id, group)
  }
  return Array.from(groups.values()).map((group) => ({
    ...group,
    selected: group.queries.every((query) => query.selected),
    separates: group.queries.some((query) => query.garment_zone === 'upper_body'),
  }))
})
const active = computed(() => directionGroups.value.filter((group) => group.selected))
const removed = computed(() => directionGroups.value.filter((group) => !group.selected))
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
      <span class="count-badge">已選擇 {{ active.length }} 組</span>
    </header>

    <div class="query-stack">
      <article v-for="group in active" :key="group.id" class="query-group">
        <header class="query-group-heading">
          <strong>方向 {{ group.id }}</strong>
          <button class="icon-button" title="移除搭配方向" :disabled="loading" @click="$emit('select', group.queries.map((query) => query.id), false)">
            <X :size="18" />
          </button>
        </header>
        <div class="query-group-rules" :class="{ separates: group.separates }">
          <section v-for="query in group.queries" :key="query.id" class="query-group-rule">
            <span class="query-zone">{{ zoneLabels[query.garment_zone] }}</span>
            <div class="query-copy">
              <strong>{{ query.rationale }}</strong>
            </div>
          </section>
        </div>
      </article>
    </div>

    <div v-if="removed.length" class="removed-queries">
      <span>已移除</span>
      <button v-for="group in removed" :key="group.id" :disabled="loading" @click="$emit('select', group.queries.map((query) => query.id), true)">
        <RotateCcw :size="14" />方向 {{ group.id }}
      </button>
    </div>

    <button class="primary-button query-search-button" :disabled="loading || !active.length" @click="$emit('search')">
      <Check :size="18" />{{ loading ? '搜尋中…' : '開始找搭配' }}
    </button>
  </section>
</template>
