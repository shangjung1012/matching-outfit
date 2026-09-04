<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Save, SlidersHorizontal } from 'lucide-vue-next'
import { getUserPreference, saveUserPreference } from '../api'
import ColorPreferenceEditor from '../components/ColorPreferenceEditor.vue'
import TagInput from '../components/TagInput.vue'
import type { UserPreference } from '../types'

const props = defineProps<{ userKey: string }>()
const preference = ref<UserPreference | null>(null)
const loading = ref(false)
const saving = ref(false)
const message = ref('')
const error = ref('')

async function load() {
  loading.value = true
  try {
    preference.value = await getUserPreference(props.userKey)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '無法載入偏好'
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!preference.value) return
  saving.value = true
  message.value = ''
  error.value = ''
  try {
    preference.value = await saveUserPreference(props.userKey, preference.value)
    message.value = '偏好已儲存，下一次 Agent 拆解需求時會參考這些設定。'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '儲存失敗'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page-view preferences-view">
    <header class="view-heading">
      <div>
        <span class="section-kicker">Profile</span>
        <h2>我的穿搭偏好</h2>
        <p>User ID：{{ userKey }}</p>
      </div>
      <button class="primary-button save-button" :disabled="saving || !preference" @click="save">
        <Save :size="17" />{{ saving ? '儲存中…' : '儲存變更' }}
      </button>
    </header>

    <div v-if="loading" class="loading-state">正在載入偏好…</div>
    <div v-else-if="preference" class="preference-form">
      <section class="form-section">
        <div class="form-section-heading">
          <h3>喜歡的顏色</h3>
          <p>Agent 會優先加入搜尋 query。</p>
        </div>
        <ColorPreferenceEditor v-model="preference.favorite_colors" />
      </section>

      <section class="form-section">
        <div class="form-section-heading">
          <h3>避免的顏色</h3>
          <p>推薦排序時應降低這些顏色的權重。</p>
        </div>
        <ColorPreferenceEditor v-model="preference.disliked_colors" />
      </section>

      <section class="form-section two-column-section">
        <div>
          <div class="form-section-heading"><h3>預算範圍</h3><p>金額單位為新台幣。</p></div>
          <div class="price-inputs">
            <label>最低<input v-model.number="preference.preferred_price_min" type="number" min="0" /></label>
            <label>最高<input v-model.number="preference.preferred_price_max" type="number" min="0" /></label>
          </div>
        </div>
        <div>
          <div class="form-section-heading"><h3>常用場合</h3><p>例如 Office、Casual、Date。</p></div>
          <TagInput v-model="preference.preferred_usages" placeholder="新增場合" />
        </div>
      </section>

      <section class="form-section preference-fields-grid">
        <label>喜歡的風格<TagInput v-model="preference.preferred_styles" placeholder="例如 minimal" /></label>
        <label>喜歡的品類<TagInput v-model="preference.preferred_categories" placeholder="例如 Topwear" /></label>
        <label>喜歡的衣服類型<TagInput v-model="preference.favorite_article_types" placeholder="例如 Tshirts" /></label>
        <label>不喜歡的衣服類型<TagInput v-model="preference.disliked_article_types" placeholder="例如 Skirts" /></label>
      </section>

      <section class="form-section">
        <label class="notes-field">其他備註<textarea v-model="preference.notes" rows="4" placeholder="版型、材質或其他需要長期記住的偏好" /></label>
      </section>

      <p v-if="message" class="success-banner">{{ message }}</p>
      <p v-if="error" class="error-banner">{{ error }}</p>
    </div>
    <div v-else class="empty-view"><SlidersHorizontal :size="32" /><h3>無法取得偏好資料</h3></div>
  </section>
</template>
