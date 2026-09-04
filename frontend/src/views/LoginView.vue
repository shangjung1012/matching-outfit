<script setup lang="ts">
import { ref } from 'vue'
import { useToast } from '../composables/useToast'

const emit = defineEmits<{ login: [userKey: string] }>()
const { showError } = useToast()

const name = ref('')

function submit() {
  const trimmed = name.value.trim()
  if (!trimmed) {
    showError('請輸入使用者名稱。')
    return
  }
  if (trimmed.length > 120) {
    showError('使用者名稱請在 120 字以內。')
    return
  }
  emit('login', trimmed)
}
</script>

<template>
  <div class="login-shell">
    <form class="login-card" @submit.prevent="submit">
      <div class="login-wordmark">
        <strong>Matching Outfit</strong>
        <small>個人穿搭</small>
      </div>
      <h2>輸入使用者名稱開始使用</h2>
      <input v-model="name" maxlength="120" autofocus autocomplete="username" />
      <button type="submit" class="primary-button">開始使用</button>
    </form>
  </div>
</template>
