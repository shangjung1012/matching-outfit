<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Plus, Save, SlidersHorizontal, Trash2 } from 'lucide-vue-next'
import {
  addStylePreference,
  deleteStylePreference,
  getPreferenceBundle,
  patchStylePreference,
  saveHardRules,
} from '../api'
import ColorPreferenceEditor from '../components/ColorPreferenceEditor.vue'
import TagInput from '../components/TagInput.vue'
import type {
  HardRules,
  PreferenceAxis,
  PreferencePolarity,
  PreferenceZone,
  StylePreference,
} from '../types'

const props = defineProps<{ userKey: string }>()

const AXES: PreferenceAxis[] = [
  'style', 'color', 'silhouette', 'material', 'article_type', 'pattern', 'length', 'fit', 'brand',
]
const ZONES: PreferenceZone[] = ['any', 'upper_body', 'lower_body', 'one_piece', 'accessory']

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

const LIST_KEYS = [
  'avoid_colours', 'avoid_article_types', 'avoid_master_categories',
] as const

const hard = reactive<HardRules>(emptyHard())
const soft = ref<StylePreference[]>([])
const loading = ref(false)
const savingHard = ref(false)
const message = ref('')
const error = ref('')

const newRow = reactive<{
  axis: PreferenceAxis
  term: string
  zone: PreferenceZone
  polarity: PreferencePolarity
  weight: number
}>({ axis: 'style', term: '', zone: 'any', polarity: 'prefer', weight: 0.3 })

/** Merge an API payload onto `hard`, never letting a list field become null/undefined. */
function applyHard(source: Partial<HardRules> | null | undefined): void {
  Object.assign(hard, emptyHard(), source ?? {})
  for (const key of LIST_KEYS) {
    if (!Array.isArray(hard[key])) hard[key] = []
  }
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
    message.value = '硬性條件已儲存，之後搜尋時會直接過濾掉不符合的單品。'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '儲存失敗'
  } finally {
    savingHard.value = false
  }
}

async function addSoft() {
  if (!newRow.term.trim()) return
  error.value = ''
  try {
    const row = await addStylePreference(props.userKey, {
      axis: newRow.axis,
      value: newRow.term.trim().toLowerCase(),
      zone: newRow.zone,
      polarity: newRow.polarity,
      weight: newRow.weight,
      source: 'explicit',
      origin: 'settings',
      origin_item_ids: [],
      context_occasions: [],
      context_seasons: [],
      context_climates: [],
    })
    soft.value = [...soft.value.filter((item) => item.id !== row.id), row]
    newRow.term = ''
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '新增失敗'
  }
}

async function toggleActive(row: StylePreference) {
  const updated = await patchStylePreference(props.userKey, row.id, { is_active: !row.is_active })
  soft.value = soft.value.map((item) => (item.id === row.id ? updated : item))
}

async function removeSoft(row: StylePreference) {
  await deleteStylePreference(props.userKey, row.id)
  soft.value = soft.value.filter((item) => item.id !== row.id)
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
    </header>

    <div v-if="loading" class="loading-state">正在載入偏好…</div>
    <div v-else class="preference-form">
      <!-- ============ HARD：硬性條件（直接過濾） ============ -->
      <section class="form-section">
        <div class="form-section-heading">
          <h3>硬性條件（Gate）</h3>
          <p>不符合的單品會在搜尋階段直接被排除。</p>
        </div>

        <div class="two-column-section">
          <div>
            <div class="form-section-heading"><h4>價格範圍</h4></div>
            <div class="price-inputs">
              <label>最低<input v-model.number="hard.price_min" type="number" min="0" /></label>
              <label>最高<input v-model.number="hard.price_max" type="number" min="0" /></label>
            </div>
          </div>
        </div>

        <div class="form-section-heading"><h4>避免的顏色</h4></div>
        <ColorPreferenceEditor v-model="hard.avoid_colours" />

        <div class="form-section-heading"><h4>避免的衣服類型</h4></div>
        <TagInput v-model="hard.avoid_article_types" placeholder="例如 Skirts" />

        <label class="notes-field">硬性備註（Agent 必須遵守）
          <textarea v-model="hard.notes" rows="3" placeholder="例如：一定要有口袋" />
        </label>

        <button class="primary-button save-button" :disabled="savingHard" @click="saveHard">
          <Save :size="17" />{{ savingHard ? '儲存中…' : '儲存硬性條件' }}
        </button>
      </section>

      <!-- ============ SOFT：軟性偏好（加權評分） ============ -->
      <section class="form-section">
        <div class="form-section-heading">
          <h3>軟性偏好（加權）</h3>
          <p>不會淘汰單品，只在排序時加減分。可隨時關閉或刪除。</p>
        </div>

        <ul v-if="soft.length" class="soft-pref-list">
          <li v-for="row in soft" :key="row.id" :class="{ inactive: !row.is_active }">
            <span class="soft-pref-tag" :class="row.polarity">
              {{ row.polarity === 'prefer' ? '偏好' : '避免' }}
            </span>
            <span class="soft-pref-body">
              <strong>{{ row.axis }}</strong> = {{ row.value }}
              <em v-if="row.zone !== 'any'">（{{ row.zone }}）</em>
              <span class="soft-pref-weight">權重 {{ row.weight.toFixed(2) }}</span>
              <span v-if="row.source === 'implicit'" class="soft-pref-src">從收藏學到</span>
            </span>
            <span class="soft-pref-actions">
              <button class="secondary-button" @click="toggleActive(row)">
                {{ row.is_active ? '停用' : '啟用' }}
              </button>
              <button class="icon-button" title="刪除" @click="removeSoft(row)"><Trash2 :size="15" /></button>
            </span>
          </li>
        </ul>
        <p v-else class="empty-hint">還沒有軟性偏好。</p>

        <div class="soft-pref-add">
          <select v-model="newRow.axis">
            <option v-for="axis in AXES" :key="axis" :value="axis">{{ axis }}</option>
          </select>
          <input v-model="newRow.term" placeholder="值，例如 japanese / light / linen" @keyup.enter="addSoft" />
          <select v-model="newRow.zone">
            <option v-for="zone in ZONES" :key="zone" :value="zone">{{ zone }}</option>
          </select>
          <select v-model="newRow.polarity">
            <option value="prefer">偏好</option>
            <option value="avoid">避免</option>
          </select>
          <label class="weight-input">權重
            <input v-model.number="newRow.weight" type="number" min="0" max="1" step="0.05" />
          </label>
          <button class="primary-button" @click="addSoft"><Plus :size="15" />新增</button>
        </div>
      </section>

      <p v-if="message" class="success-banner">{{ message }}</p>
      <p v-if="error" class="error-banner">{{ error }}</p>
    </div>

    <div v-if="!loading && error && !soft.length" class="empty-view">
      <SlidersHorizontal :size="32" /><h3>{{ error }}</h3>
    </div>
  </section>
</template>
