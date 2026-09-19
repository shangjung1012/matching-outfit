<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ modelValue: string[] | null }>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

const selected = computed(() => props.modelValue ?? [])

const colors = [
  { name: 'Black', value: '#202020' },
  { name: 'White', value: '#f5f5f2' },
  { name: 'Grey', value: '#969b9b' },
  { name: 'Beige', value: '#d8c8a6' },
  { name: 'Blue', value: '#3f6fa5' },
  { name: 'Green', value: '#52785b' },
  { name: 'Red', value: '#ad4643' },
  { name: 'Pink', value: '#d590a2' },
  { name: 'Purple', value: '#8162a7' },
  { name: 'Orange', value: '#d77a35' },
  { name: 'Yellow', value: '#d2ac3a' },
  { name: 'Turquoise', value: '#37a5a1' },
  { name: 'Metallic', value: '#b09b65' },
]

function toggle(name: string) {
  const current = selected.value
  emit('update:modelValue', current.includes(name)
    ? current.filter((color) => color !== name)
    : [...current, name])
}
</script>

<template>
  <div class="color-options">
    <button
      v-for="color in colors"
      :key="color.name"
      type="button"
      :class="{ selected: selected.includes(color.name) }"
      @click="toggle(color.name)"
    >
      <i :style="{ backgroundColor: color.value }" />
      {{ color.name }}
    </button>
  </div>
</template>
