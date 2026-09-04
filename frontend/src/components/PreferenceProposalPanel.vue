<script setup lang="ts">
import { Check, X } from 'lucide-vue-next'
import type { PreferenceProposal } from '../types'

defineProps<{ proposal: PreferenceProposal; loading: boolean }>()
defineEmits<{ confirm: []; dismiss: [] }>()
</script>

<template>
  <section class="preference-proposal">
    <div>
      <span class="section-kicker">Preference update</span>
      <h3>要把這次的喜好記下來嗎？</h3>
      <p>喜歡的顏色：{{ proposal.favorite_colors_to_add.join('、') || '沒有新增項目' }}</p>
      <p>喜歡的品類：{{ proposal.favorite_article_types_to_add.join('、') || '沒有新增項目' }}</p>
    </div>
    <div class="proposal-actions">
      <button class="secondary-button" @click="$emit('dismiss')"><X :size="16" />先不要</button>
      <button class="primary-button" :disabled="loading" @click="$emit('confirm')"><Check :size="16" />確認更新</button>
    </div>
  </section>
</template>
