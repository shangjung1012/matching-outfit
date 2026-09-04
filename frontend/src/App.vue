<script setup lang="ts">
import { ref } from 'vue'
import LoginView from './views/LoginView.vue'
import MainApp from './MainApp.vue'

const CURRENT_USER_STORAGE_KEY = 'matching-outfit.current-user'

function loadStoredUser(): string | null {
  try {
    return localStorage.getItem(CURRENT_USER_STORAGE_KEY)
  } catch {
    return null
  }
}

const userKey = ref<string | null>(loadStoredUser())

function login(name: string) {
  try {
    localStorage.setItem(CURRENT_USER_STORAGE_KEY, name)
  } catch {
    // localStorage 不可用時仍可繼續使用，只是不會記住登入狀態
  }
  userKey.value = name
}

function logout() {
  try {
    localStorage.removeItem(CURRENT_USER_STORAGE_KEY)
  } catch {
    // ignore
  }
  userKey.value = null
}
</script>

<template>
  <LoginView v-if="!userKey" @login="login" />
  <MainApp v-else :key="userKey" :user-key="userKey" @logout="logout" />
</template>
