<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Brain, Check, Pencil, Plus, Save, ShieldCheck, Trash2, X } from 'lucide-vue-next'
import {
  addStylePreference,
  deleteStylePreference,
  getPreferenceBundle,
  patchStylePreference,
  saveHardRules,
} from '../api'
import ColorPreferenceEditor from '../components/ColorPreferenceEditor.vue'
import TagInput from '../components/TagInput.vue'
import type { HardRules, StylePreference } from '../types'

const props = defineProps<{ userKey: string }>()

function emptyHard(): HardRules {
  return {
    price_min: null,
    price_max: null,
    avoid_colours: [],
    avoid_article_types: [],
    avoid_master_categories: [],
    notes: null,
  }
}

const hard = reactive<HardRules>(emptyHard())
const soft = ref<StylePreference[]>([])
const newPreference = reactive({ text: '', occasion: '', time: '', situation: '' })
const editingId = ref<number | null>(null)
const editingText = ref('')
const loading = ref(false)
const savingHard = ref(false)
const message = ref('')
const error = ref('')

function applyHard(source: Partial<HardRules> | null | undefined): void {
  Object.assign(hard, emptyHard(), source ?? {})
  if (!Array.isArray(hard.avoid_colours)) hard.avoid_colours = []
  if (!Array.isArray(hard.avoid_article_types)) hard.avoid_article_types = []
  if (!Array.isArray(hard.avoid_master_categories)) hard.avoid_master_categories = []
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const bundle = await getPreferenceBundle(props.userKey)
    applyHard(bundle?.hard)
    soft.value = Array.isArray(bundle?.soft) ? bundle.soft : []
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '無法載入偏好'
  } finally {
    loading.value = false
  }
}

async function saveHard() {
  savingHard.value = true
  message.value = ''
  error.value = ''
  try {
    const saved = await saveHardRules(props.userKey, { ...hard })
    applyHard(saved)
    message.value = '購物條件已儲存'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '儲存失敗'
  } finally {
    savingHard.value = false
  }
}

async function addSoft() {
  const preferenceText = newPreference.text.trim()
  if (!preferenceText) return
  error.value = ''
  try {
    const row = await addStylePreference(props.userKey, {
      preference_text: preferenceText,
      source: 'explicit',
      origin_item_ids: [],
      context_occasions: newPreference.occasion.trim() ? [newPreference.occasion.trim()] : [],
      context_times: newPreference.time.trim() ? [newPreference.time.trim()] : [],
      context_situations: newPreference.situation.trim() ? [newPreference.situation.trim()] : [],
    })
    soft.value = [...soft.value.filter((item) => item.id !== row.id), row]
    Object.assign(newPreference, { text: '', occasion: '', time: '', situation: '' })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '新增失敗'
  }
}

async function toggleActive(row: StylePreference) {
  const updated = await patchStylePreference(props.userKey, row.id, {
    is_active: !row.is_active,
  })
  soft.value = soft.value.map((item) => (item.id === row.id ? updated : item))
}

function beginEdit(row: StylePreference) {
  editingId.value = row.id
  editingText.value = row.preference_text
}

async function saveEdit(row: StylePreference) {
  const text = editingText.value.trim()
  if (!text) return
  const updated = await patchStylePreference(props.userKey, row.id, {
    preference_text: text,
  })
  soft.value = soft.value.map((item) => (item.id === row.id ? updated : item))
  editingId.value = null
}

async function removeSoft(row: StylePreference) {
  await deleteStylePreference(props.userKey, row.id)
  soft.value = soft.value.filter((item) => item.id !== row.id)
}

function preferenceContexts(row: StylePreference): string[] {
  return [
    ...row.context_occasions,
    ...row.context_times,
    ...row.context_situations,
  ]
}

onMounted(load)
</script>

<template>
  <section class="page-view preferences-view">
    <header class="view-heading preferences-heading">
      <div>
        <h2>偏好設定</h2>
        <p>{{ userKey }}</p>
      </div>
    </header>

    <div v-if="loading" class="loading-state">正在載入</div>
    <div v-else class="preference-form">
      <section class="settings-section">
        <header class="settings-section-heading">
          <ShieldCheck :size="20" />
          <h3>購物條件</h3>
        </header>

        <div class="settings-list">
          <div class="settings-row price-settings-row">
            <div class="settings-label"><strong>價格範圍</strong></div>
            <div class="price-inputs">
              <label>最低價格<input v-model.number="hard.price_min" type="number" min="0" /></label>
              <label>最高價格<input v-model.number="hard.price_max" type="number" min="0" /></label>
            </div>
          </div>

          <div class="settings-row">
            <div class="settings-label"><strong>排除顏色</strong></div>
            <ColorPreferenceEditor v-model="hard.avoid_colours" />
          </div>

          <div class="settings-row">
            <div class="settings-label"><strong>排除衣服類型</strong></div>
            <TagInput v-model="hard.avoid_article_types" placeholder="輸入衣服類型" />
          </div>

          <div class="settings-row">
            <label class="settings-label" for="required-details"><strong>其他必要條件</strong></label>
            <textarea id="required-details" v-model="hard.notes" rows="3" />
          </div>
        </div>

        <div class="settings-actions">
          <button class="primary-button" :disabled="savingHard" @click="saveHard">
            <Save :size="17" />{{ savingHard ? '儲存中' : '儲存變更' }}
          </button>
        </div>
      </section>

      <section class="settings-section">
        <header class="settings-section-heading">
          <Brain :size="20" />
          <h3>穿搭記憶</h3>
        </header>

        <ul v-if="soft.length" class="memory-list">
          <li v-for="row in soft" :key="row.id" :class="{ inactive: !row.is_active }">
            <div class="memory-content">
              <template v-if="editingId === row.id">
                <textarea v-model="editingText" rows="3" />
                <div class="memory-edit-actions">
                  <button class="icon-button" title="取消編輯" @click="editingId = null"><X :size="15" /></button>
                  <button class="icon-button dark" title="儲存偏好" @click="saveEdit(row)"><Check :size="15" /></button>
                </div>
              </template>
              <template v-else>
                <p>{{ row.preference_text }}</p>
                <div v-if="preferenceContexts(row).length" class="memory-contexts">
                  <span v-for="context in preferenceContexts(row)" :key="context">{{ context }}</span>
                </div>
              </template>
            </div>
            <div class="memory-actions">
              <button
                class="preference-toggle"
                :class="{ active: row.is_active }"
                role="switch"
                :aria-checked="row.is_active"
                :title="row.is_active ? '停用' : '啟用'"
                @click="toggleActive(row)"
              ><span /></button>
              <button class="icon-button" title="編輯" @click="beginEdit(row)"><Pencil :size="15" /></button>
              <button class="icon-button danger" title="刪除" @click="removeSoft(row)"><Trash2 :size="15" /></button>
            </div>
          </li>
        </ul>
        <div v-else class="memory-empty"><Brain :size="24" /><span>尚無穿搭記憶</span></div>

        <div class="memory-create">
          <label>新增偏好<textarea v-model="newPreference.text" rows="3" /></label>
          <div class="memory-context-inputs">
            <label>場合<input v-model="newPreference.occasion" /></label>
            <label>時間<input v-model="newPreference.time" /></label>
            <label>情境<input v-model="newPreference.situation" /></label>
          </div>
          <button class="secondary-button" :disabled="!newPreference.text.trim()" @click="addSoft">
            <Plus :size="16" />新增偏好
          </button>
        </div>
      </section>

      <p v-if="message" class="success-banner">{{ message }}</p>
      <p v-if="error" class="error-banner">{{ error }}</p>
    </div>
  </section>
</template>
