<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Brain, Check, Pencil, Plus, Save, ShieldCheck, Trash2, UserRound, X } from 'lucide-vue-next'
import {
  saveHardRules,
} from '../api'
import ColorPreferenceEditor from '../components/ColorPreferenceEditor.vue'
import TagInput from '../components/TagInput.vue'
import { useUserLibrary } from '../composables/useUserLibrary'
import { useToast } from '../composables/useToast'
import type { HardRules, StylePreference } from '../types'

const props = defineProps<{ userKey: string }>()
const {
  stylePreferences: soft,
  loadPreferences,
  addPreference,
  patchPreference,
  removePreference,
} = useUserLibrary(props.userKey)
const { showError, showSuccess } = useToast()

function emptyHard(): HardRules {
  return {
    gender: null,
    age: null,
    height_cm: null,
    weight_kg: null,
    price_min: null,
    price_max: null,
    avoid_colours: [],
    avoid_article_types: [],
    avoid_master_categories: [],
    notes: null,
  }
}

const hard = reactive<HardRules>(emptyHard())
const newPreference = reactive({ text: '' })
const editingId = ref<number | null>(null)
const editingText = ref('')
const loading = ref(false)
const savingHard = ref(false)

function applyHard(source: Partial<HardRules> | null | undefined): void {
  Object.assign(hard, emptyHard(), source ?? {})
  if (!Array.isArray(hard.avoid_colours)) hard.avoid_colours = []
  if (!Array.isArray(hard.avoid_article_types)) hard.avoid_article_types = []
  if (!Array.isArray(hard.avoid_master_categories)) hard.avoid_master_categories = []
}

async function load() {
  loading.value = true
  try {
    const bundle = await loadPreferences()
    applyHard(bundle?.hard)
    soft.value = Array.isArray(bundle?.soft) ? bundle.soft : []
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '無法載入偏好')
  } finally {
    loading.value = false
  }
}

async function saveHard() {
  savingHard.value = true
  try {
    const saved = await saveHardRules(props.userKey, {
      ...hard,
      age: hard.age || null,
      height_cm: hard.height_cm || null,
      weight_kg: hard.weight_kg || null,
      price_min: hard.price_min || null,
      price_max: hard.price_max || null,
    })
    applyHard(saved)
    showSuccess('個人資料與購物條件已儲存')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '儲存失敗')
  } finally {
    savingHard.value = false
  }
}

async function addSoft() {
  const preferenceText = newPreference.text.trim()
  if (!preferenceText) return
  try {
    await addPreference({
      preference_text: preferenceText,
      preference_type: 'prefer',
      source: 'explicit',
      origin_item_ids: [],
      occasions: [],
      seasons: [],
      times_of_day: [],
      climates: [],
      formalities: [],
      activities: [],
      styles: [],
    })
    newPreference.text = ''
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '新增失敗')
  }
}

async function toggleActive(row: StylePreference) {
  await patchPreference(row.id, {
    is_active: !row.is_active,
  })
}

function beginEdit(row: StylePreference) {
  editingId.value = row.id
  editingText.value = row.preference_text
}

async function saveEdit(row: StylePreference) {
  const text = editingText.value.trim()
  if (!text) return
  await patchPreference(row.id, {
    preference_text: text,
  })
  editingId.value = null
}

async function removeSoft(row: StylePreference) {
  await removePreference(row.id)
}

function preferenceContexts(row: StylePreference): string[] {
  return [
    ...row.occasions,
    ...row.seasons,
    ...row.times_of_day,
    ...row.climates,
    ...row.formalities,
    ...row.activities,
    ...row.styles,
  ]
}

onMounted(load)
</script>

<template>
  <section class="page-view preferences-view">
    <header class="view-heading preferences-heading">
      <div>
        <span class="section-kicker">Preferences</span>
        <h2>偏好設定</h2>
      </div>
    </header>

    <div v-if="loading" class="loading-state">正在載入</div>
    <div v-else class="preference-form">
      <section class="settings-section">
        <header class="settings-section-heading">
          <UserRound :size="20" />
          <h3>個人資料</h3>
        </header>

        <div class="settings-list profile-settings-list">
          <label class="profile-field">
            <span>性別</span>
            <select v-model="hard.gender">
              <option :value="null">未設定</option>
              <option value="female">女性</option>
              <option value="male">男性</option>
              <option value="non_binary">非二元</option>
              <option value="prefer_not_to_say">不透露</option>
            </select>
          </label>
          <label class="profile-field">
            <span>年齡</span>
            <input v-model.number="hard.age" type="number" min="1" max="120" />
          </label>
          <label class="profile-field">
            <span>身高</span>
            <div class="unit-input">
              <input v-model.number="hard.height_cm" type="number" min="50" max="250" />
              <span>cm</span>
            </div>
          </label>
          <label class="profile-field">
            <span>體重</span>
            <div class="unit-input">
              <input v-model.number="hard.weight_kg" type="number" min="10" max="400" />
              <span>kg</span>
            </div>
          </label>
        </div>
      </section>

      <section class="settings-section">
        <header class="settings-section-heading">
          <ShieldCheck :size="20" />
          <h3>購物條件</h3>
        </header>

        <div class="settings-list">
          <div class="settings-row price-settings-row">
            <div class="settings-label"><strong>單件商品價格範圍</strong></div>
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
          <button class="secondary-button" :disabled="!newPreference.text.trim()" @click="addSoft">
            <Plus :size="16" />新增偏好
          </button>
        </div>
      </section>

      <div class="settings-actions preference-save-actions">
        <button class="primary-button" :disabled="savingHard" @click="saveHard">
          <Save :size="17" />{{ savingHard ? '儲存中' : '儲存個人資料與條件' }}
        </button>
      </div>
    </div>
  </section>
</template>
