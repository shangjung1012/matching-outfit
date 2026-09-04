<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{ login: [userKey: string] }>()

const name = ref('')
const error = ref('')

function submit() {
  const trimmed = name.value.trim()
  if (!trimmed) {
    error.value = '請輸入使用者名稱。'
    return
  }
  if (trimmed.length > 120) {
    error.value = '使用者名稱請在 120 字以內。'
    return
  }
  error.value = ''
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
      <p v-if="error" class="login-error">{{ error }}</p>
      <button type="submit" class="primary-button">開始使用</button>
    </form>
  </div>
</template>
