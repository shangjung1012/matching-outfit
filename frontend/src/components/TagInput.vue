<script setup lang="ts">
import { ref } from 'vue'
import { Plus, X } from 'lucide-vue-next'

const props = defineProps<{ modelValue: string[]; placeholder?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const draft = ref('')

function add() {
  const value = draft.value.trim()
  if (!value || props.modelValue.some((item) => item.toLowerCase() === value.toLowerCase())) return
  emit('update:modelValue', [...props.modelValue, value])
  draft.value = ''
}

function remove(value: string) {
  emit('update:modelValue', props.modelValue.filter((item) => item !== value))
}
</script>

<template>
  <div class="tag-editor">
    <div v-if="modelValue.length" class="tag-list">
      <span v-for="item in modelValue" :key="item">
        {{ item }}
        <button :title="`移除 ${item}`" @click="remove(item)"><X :size="13" /></button>
      </span>
    </div>
    <div class="tag-entry">
      <input v-model="draft" :placeholder="placeholder || '輸入後按 Enter'" @keyup.enter="add" />
      <button class="icon-button" title="新增" @click="add"><Plus :size="17" /></button>
    </div>
  </div>
</template>
