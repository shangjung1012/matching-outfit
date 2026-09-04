<script setup lang="ts">
import { ref } from 'vue'

const prompt = ref('幫我準備一套正式場合的服裝，預算 3000 元')
const apiStatus = ref('Not checked')
const isLoading = ref(false)
const errorMessage = ref('')

async function checkApiHealth() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    const response = await fetch('/api/health')

    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`)
    }

    const body = await response.json()
    apiStatus.value = body.status
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="app-shell">
    <section class="workspace">
      <div class="request-panel">
        <p class="eyebrow">Natural-language outfit advisor</p>
        <h1>Matching Outfit</h1>

        <label>
          Shopping request
          <textarea v-model="prompt" rows="5" />
        </label>

        <button type="button" :disabled="isLoading" @click="checkApiHealth">
          {{ isLoading ? 'Checking...' : 'Check backend' }}
        </button>

        <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
      </div>

      <div class="result-panel">
        <p class="eyebrow">Current scaffold</p>
        <h2>Backend status: {{ apiStatus }}</h2>
        <div class="items">
          <article class="item-card">
            <span>model</span>
            <h3>Cloth</h3>
            <p>Stores catalog fields from styles.csv plus an integer price.</p>
          </article>
          <article class="item-card">
            <span>model</span>
            <h3>UserPreference</h3>
            <p>Stores colors, price range, style, category, and usage preferences.</p>
          </article>
        </div>
      </div>
    </section>
  </main>
</template>
