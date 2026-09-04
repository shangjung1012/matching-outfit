<script setup lang="ts">
import { Check, X } from 'lucide-vue-next'
import type { StylePreferenceProposal } from '../types'

defineProps<{ proposal: StylePreferenceProposal; loading: boolean }>()
defineEmits<{ confirm: []; dismiss: [] }>()
</script>

<template>
  <section class="preference-proposal">
    <div>
      <h3>要把這次的喜好記下來嗎？</h3>
      <ul v-if="proposal.proposals.length" class="proposal-rows">
        <li v-for="(row, index) in proposal.proposals" :key="index">
          <span>{{ row.preference_text }}</span>
        </li>
      </ul>
      <p v-else>沒有可新增的偏好項目。</p>
    </div>
    <div class="proposal-actions">
      <button class="secondary-button" @click="$emit('dismiss')"><X :size="16" />先不要</button>
      <button
        class="primary-button"
        :disabled="loading || !proposal.proposals.length"
        @click="$emit('confirm')"
      >
        <Check :size="16" />確認更新
      </button>
    </div>
  </section>
</template>
