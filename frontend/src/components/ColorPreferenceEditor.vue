<script setup lang="ts">
const props = defineProps<{ modelValue: string[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

const colors = [
  { name: 'Black', value: '#202020' },
  { name: 'White', value: '#f5f5f2' },
  { name: 'Grey', value: '#969b9b' },
  { name: 'Blue', value: '#3f6fa5' },
  { name: 'Navy Blue', value: '#243852' },
  { name: 'Red', value: '#ad4643' },
  { name: 'Green', value: '#52785b' },
  { name: 'Pink', value: '#d590a2' },
  { name: 'Beige', value: '#d8c8a6' },
  { name: 'Brown', value: '#795b48' },
]

function toggle(name: string) {
  const selected = props.modelValue.includes(name)
  emit('update:modelValue', selected
    ? props.modelValue.filter((color) => color !== name)
    : [...props.modelValue, name])
}
</script>

<template>
  <div class="color-options">
    <button
      v-for="color in colors"
      :key="color.name"
      type="button"
      :class="{ selected: modelValue.includes(color.name) }"
      @click="toggle(color.name)"
    >
      <i :style="{ backgroundColor: color.value }" />
      {{ color.name }}
    </button>
  </div>
</template>
