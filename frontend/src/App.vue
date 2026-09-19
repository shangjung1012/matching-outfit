<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import LoginView from './views/LoginView.vue'
import MainApp from './MainApp.vue'
import FashionMbtiView from './views/FashionMbtiView.vue'
import ToastContainer from './components/ToastContainer.vue'
import { loginUserProfile, updateUserProfile } from './api'
import { useToast } from './composables/useToast'
import type { UserProfile } from './types'

const CURRENT_USER_STORAGE_KEY = 'matching-outfit.current-user'
const onboardingSkipStorageKey = (userKey: string) => `matching-outfit.onboarding-skipped.${userKey}`

function loadStoredUser(): string | null {
  try {
    return localStorage.getItem(CURRENT_USER_STORAGE_KEY)
  } catch {
    return null
  }
}

const router = useRouter()
const { showError } = useToast()
const userKey = ref<string | null>(null)
const profile = ref<UserProfile | null>(null)
const onboardingSkipped = ref(false)
const onboardingTestComplete = ref(false)
const onboardingActive = ref(false)
const profileLoading = ref(true)
const showOnboarding = computed(() => userKey.value !== null && onboardingActive.value)

function skippedOnboardingFor(userKey: string): boolean {
  try {
    return sessionStorage.getItem(onboardingSkipStorageKey(userKey)) === 'true'
  } catch {
    return false
  }
}

async function enterApp(name: string) {
  const loadedProfile = await loginUserProfile(name)
  try {
    localStorage.setItem(CURRENT_USER_STORAGE_KEY, loadedProfile.user_key)
  } catch {
    // localStorage 不可用時仍可繼續使用，只是不會記住登入狀態
  }
  userKey.value = loadedProfile.user_key
  profile.value = loadedProfile
  onboardingSkipped.value = skippedOnboardingFor(loadedProfile.user_key)
  onboardingTestComplete.value = false
  onboardingActive.value = !loadedProfile.do_test && !onboardingSkipped.value
  if (!onboardingActive.value) {
    await router.replace({ name: 'agent' })
  }
}

async function login(name: string) {
  try {
    await enterApp(name)
  } catch (error) {
    showError(error instanceof Error ? error.message : '無法載入使用者設定。')
  }
}

function logout() {
  const currentUserKey = userKey.value
  try {
    localStorage.removeItem(CURRENT_USER_STORAGE_KEY)
  } catch {
    // ignore
  }
  if (currentUserKey) {
    try {
      sessionStorage.removeItem(onboardingSkipStorageKey(currentUserKey))
    } catch {
      // ignore
    }
  }
  userKey.value = null
  profile.value = null
  onboardingSkipped.value = false
  onboardingTestComplete.value = false
  onboardingActive.value = false
  void router.replace({ name: 'agent' })
}

async function skipOnboarding() {
  if (!userKey.value) return
  if (!profile.value?.do_test) {
    try {
      sessionStorage.setItem(onboardingSkipStorageKey(userKey.value), 'true')
    } catch {
      // Keep the current-tab behavior even when sessionStorage is unavailable.
    }
  }
  onboardingSkipped.value = true
  onboardingActive.value = false
  await router.replace({ name: 'agent' })
}

async function updateOnboardingStage(stage: 'landing' | 'quiz' | 'result') {
  if (stage !== 'result' || !profile.value || profile.value.do_test) return
  try {
    profile.value = await updateUserProfile(profile.value.user_key, { do_test: true })
    onboardingTestComplete.value = true
  } catch (error) {
    showError(error instanceof Error ? error.message : '無法儲存測驗完成狀態。')
  }
}

onMounted(async () => {
  const storedUser = loadStoredUser()
  if (storedUser) {
    try {
      await enterApp(storedUser)
    } catch {
      // Keep the login screen available when the profile service is unavailable.
    }
  }
  profileLoading.value = false
})
</script>

<template>
  <div v-if="profileLoading" class="login-shell" aria-label="載入使用者設定" />
  <LoginView v-else-if="!userKey" @login="login" />
  <section v-else-if="showOnboarding" class="onboarding-shell">
    <header class="onboarding-header">
      <div class="onboarding-wordmark"><strong>潮會搭</strong><small>個人穿搭</small></div>
      <button type="button" class="onboarding-skip" @click="skipOnboarding">
        {{ onboardingTestComplete ? '進入主頁' : '略過測驗' }}
      </button>
    </header>
    <FashionMbtiView :user-key="userKey" @stage-change="updateOnboardingStage" />
  </section>
  <MainApp v-else :key="userKey" :user-key="userKey" @logout="logout" />
  <ToastContainer />
</template>
