<script setup lang="ts">
import { computed } from 'vue'
import { Check, RotateCcw, X } from 'lucide-vue-next'
import type { QueryDraft } from '../types'

const props = defineProps<{ queries: QueryDraft[]; loading: boolean }>()
const emit = defineEmits<{
  select: [id: string, selected: boolean]
  updateText: [id: string, text: string]
  search: []
}>()

const active = computed(() => props.queries.filter((query) => query.selected))
const removed = computed(() => props.queries.filter((query) => !query.selected))
</script>

<template>
  <section class="query-review">
    <header class="view-heading compact-heading">
      <div>
        <span class="section-kicker">Search plan</span>
        <h2>確認搜尋條件</h2>
        <p>保留需要的 query，也可以直接修改英文內容。</p>
      </div>
      <span class="count-badge">{{ active.length }} selected</span>
    </header>

    <div class="query-stack">
      <article v-for="query in active" :key="query.id" class="query-item">
        <span class="query-zone">{{ query.garment_zone.replace('_', ' ') }}</span>
        <div class="query-copy">
          <input
            :value="query.text"
            aria-label="搜尋 query"
            @input="$emit('updateText', query.id, ($event.target as HTMLInputElement).value)"
          />
          <p>{{ query.rationale }}</p>
        </div>
        <button class="icon-button" title="移除 query" @click="$emit('select', query.id, false)">
          <X :size="18" />
        </button>
      </article>
    </div>

    <div v-if="removed.length" class="removed-queries">
      <span>已移除</span>
      <button v-for="query in removed" :key="query.id" @click="$emit('select', query.id, true)">
        <RotateCcw :size="14" />{{ query.garment_zone.replace('_', ' ') }}
      </button>
    </div>

    <button class="primary-button query-search-button" :disabled="loading || !active.length" @click="$emit('search')">
      <Check :size="18" />{{ loading ? '搜尋中…' : '確認並搜尋搭配' }}
    </button>
  </section>
</template>
