<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, Check, Download, RotateCcw, SlidersHorizontal } from 'lucide-vue-next'
import {
  MBTI_AXES,
  MBTI_QUESTIONS,
  computeMbtiResult,
  loadMbtiState,
  saveMbtiState,
} from '../data/fashionMbti'
import { useUserLibrary } from '../composables/useUserLibrary'
import { useToast } from '../composables/useToast'
import { renderMbtiCard, saveMbtiCard } from '../utils/mbtiCard'
import type { FashionMbtiAnswer, FashionMbtiOption, FashionMbtiResult } from '../types'

const MBTI_ORIGIN = ['fashion-mbti']

const props = defineProps<{ userKey: string }>()
const {
  stylePreferences,
  loadPreferences,
  confirmPreferences,
  deactivatePreferenceOrigin,
} = useUserLibrary(props.userKey)
const { showError, showSuccess } = useToast()

type Stage = 'landing' | 'quiz' | 'result'

const stage = ref<Stage>('landing')
const answers = ref<FashionMbtiAnswer[]>([])
const index = ref(0)
const picked = ref<string>('')
const result = ref<FashionMbtiResult | null>(null)
const storedResult = ref<FashionMbtiResult | null>(null)
const confirmingRetake = ref(false)
const savingPreference = ref(false)
const cardCanvas = ref<HTMLCanvasElement | null>(null)
let advanceTimer: number | undefined

const question = computed(() => MBTI_QUESTIONS[index.value])
const total = MBTI_QUESTIONS.length

/** 回到上一題時，把原本選過的答案標回來。 */
const currentAnswerId = computed(
  () => answers.value.find((row) => row.questionId === question.value.id)?.optionId ?? '',
)

const bars = computed(() => {
  const scores = result.value?.scores
  if (!scores) return []
  const leftValues = [scores.comfort, scores.budget, scores.modest, scores.neutral]
  return MBTI_AXES.map((axis, position) => {
    const leftPct = leftValues[position]
    return {
      id: axis.id,
      title: axis.title,
      leftLabel: axis.aLabel,
      rightLabel: axis.bLabel,
      leftPct,
      rightPct: 100 - leftPct,
      leftLeads: leftPct >= 50,
      leadPct: Math.max(leftPct, 100 - leftPct),
    }
  })
})

function persist() {
  saveMbtiState(props.userKey, {
    result: result.value ?? storedResult.value,
    progress: stage.value === 'quiz' ? answers.value : [],
  })
}

function start() {
  answers.value = []
  index.value = 0
  picked.value = ''
  stage.value = 'quiz'
  persist()
}

function resume() {
  stage.value = 'quiz'
}

function showStored() {
  result.value = storedResult.value
  stage.value = 'result'
}

function finish() {
  const outcome = computeMbtiResult(answers.value)
  result.value = outcome
  storedResult.value = outcome
  stage.value = 'result'
  confirmingRetake.value = false
  persist()
}

function choose(option: FashionMbtiOption) {
  if (advanceTimer) return
  picked.value = option.id
  const next = answers.value.filter((row) => row.questionId !== question.value.id)
  next.push({ questionId: question.value.id, optionId: option.id })
  answers.value = next.sort((left, right) => left.questionId - right.questionId)

  // 短暫停留讓選取狀態看得見，再換下一題。
  advanceTimer = window.setTimeout(() => {
    advanceTimer = undefined
    picked.value = ''
    if (index.value + 1 >= total) {
      finish()
      return
    }
    index.value += 1
    persist()
  }, 180)
}

function back() {
  if (index.value === 0) return
  index.value -= 1
  picked.value = ''
}

function retake() {
  if (storedResult.value && !confirmingRetake.value) {
    confirmingRetake.value = true
    return
  }
  confirmingRetake.value = false
  start()
}

function preferenceText(row: FashionMbtiResult): string {
  const { scores } = row
  const balance = [
    scores.comfort >= 50 ? `舒適 ${scores.comfort}%` : `造型感 ${scores.style}%`,
    scores.budget >= 50 ? `實惠 ${scores.budget}%` : `高價 ${scores.invest}%`,
    scores.modest >= 50 ? `包覆 ${scores.modest}%` : `露膚 ${scores.open}%`,
    scores.neutral >= 50 ? `素色 ${scores.neutral}%` : `彩色 ${scores.vivid}%`,
  ].join('、')
  return `穿搭人格 ${row.code}「${row.name}」：${balance}。${row.description}`.slice(0, 500)
}

const savedPreference = computed(() =>
  stylePreferences.value.find(
    (row) => row.is_active && row.origin_item_ids.join(':') === MBTI_ORIGIN.join(':'),
  ) ?? null,
)
const alreadySaved = computed(
  () => !!result.value && savedPreference.value?.preference_text === preferenceText(result.value),
)

async function saveToPreferences() {
  if (!result.value || savingPreference.value) return
  savingPreference.value = true
  try {
    // 先停用上一次的穿搭人格偏好，同時間只保留一組。
    await deactivatePreferenceOrigin(MBTI_ORIGIN)
    await confirmPreferences([
      {
        preference_text: preferenceText(result.value),
        preference_type: 'prefer',
        source: 'explicit',
        origin_item_ids: MBTI_ORIGIN,
        occasions: [],
        seasons: [],
        times_of_day: [],
        climates: [],
        formalities: [],
        activities: [],
        styles: result.value.keywords,
      },
    ])
    showSuccess('已寫入「我的偏好」，之後規劃穿搭時會參考這組風格。')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '寫入偏好失敗')
  } finally {
    savingPreference.value = false
  }
}

async function saveImage() {
  if (!cardCanvas.value || !result.value) return
  try {
    await saveMbtiCard(cardCanvas.value, result.value.code)
    showSuccess('已下載穿搭人格圖片。')
  } catch {
    showError('圖片產生失敗，請再試一次。')
  }
}

function handleKey(event: KeyboardEvent) {
  if (stage.value !== 'quiz' || event.metaKey || event.ctrlKey || event.altKey) return
  const target = event.target as HTMLElement | null
  if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return

  if (event.key === 'Backspace' || event.key === 'ArrowLeft') {
    event.preventDefault()
    back()
    return
  }
  const key = event.key.toUpperCase()
  const position = 'ABCD'.indexOf(key) >= 0 ? 'ABCD'.indexOf(key) : Number(key) - 1
  const option = question.value.options[position]
  if (option) {
    event.preventDefault()
    choose(option)
  }
}

watch([() => stage.value, () => result.value], async () => {
  if (stage.value !== 'result' || !result.value) return
  await nextTick()
  if (cardCanvas.value) await renderMbtiCard(cardCanvas.value, result.value)
})

onMounted(() => {
  const state = loadMbtiState(props.userKey)
  storedResult.value = state.result
  if (state.progress.length && state.progress.length < total) {
    answers.value = state.progress
    index.value = state.progress.length
  } else if (state.result) {
    result.value = state.result
    stage.value = 'result'
  }
  window.addEventListener('keydown', handleKey)
  void loadPreferences().catch(() => undefined)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKey)
  if (advanceTimer) window.clearTimeout(advanceTimer)
  persist()
})
</script>

<template>
  <section class="page-view mbti-view">
    <div v-if="stage === 'landing'" class="mbti-landing">
      <div class="mbti-landing-copy">
        <span class="section-kicker">Fashion MBTI</span>
        <h2>你的穿搭<em>人格</em>是哪一種？</h2>
        <p>11 個生活情境，一題一個直覺選擇，最後給你一組四個字母的穿搭人格與完整分數。</p>
        <div class="mbti-landing-actions">
          <button class="primary-button" @click="start">
            開始測驗<ArrowRight :size="16" />
          </button>
          <button
            v-if="answers.length"
            class="secondary-button"
            @click="resume"
          >
            繼續上次的第 {{ answers.length + 1 }} 題
          </button>
          <button
            v-else-if="storedResult"
            class="secondary-button"
            @click="showStored"
          >
            看上次的結果 · {{ storedResult.code }}
          </button>
        </div>
      </div>
      <ol class="mbti-letter-wall" aria-hidden="true">
        <li v-for="letter in ['C', 'S', 'B', 'I', 'M', 'O', 'N', 'V']" :key="letter">{{ letter }}</li>
      </ol>
    </div>

    <!-- 作答 -->
    <div v-else-if="stage === 'quiz'" class="mbti-quiz">
      <div class="mbti-progress">
        <span class="mbti-progress-count"><b>{{ index + 1 }}</b> / {{ total }}</span>
        <ol class="mbti-ticks">
          <li
            v-for="step in total"
            :key="step"
            :class="{ done: step <= index, current: step === index + 1 }"
          />
        </ol>
      </div>

      <Transition name="mbti-swap" mode="out-in">
        <article :key="question.id" class="mbti-question">
          <p class="mbti-question-index">Q{{ index + 1 }}</p>
          <h2>{{ question.prompt }}</h2>

          <ul class="mbti-options" :class="{ visual: question.visual }">
            <li v-for="option in question.options" :key="option.id">
              <button
                :class="{ picked: picked ? picked === option.id : currentAnswerId === option.id }"
                @click="choose(option)"
              >
                <span class="mbti-option-mark">{{ option.id }}</span>
                <span class="mbti-option-body">
                  <img
                    v-if="option.image"
                    class="mbti-option-image"
                    :src="option.image"
                    :alt="`選項 ${option.id}`"
                  />
                  <span class="mbti-option-label">{{ option.label }}</span>
                </span>
              </button>
            </li>
          </ul>
        </article>
      </Transition>

      <footer class="mbti-quiz-footer">
        <button v-if="index > 0" class="mbti-text-button" @click="back">
          <ArrowLeft :size="15" />上一題
        </button>
        <span v-else />
        <span />
      </footer>
    </div>

    <!-- 結果 -->
    <div v-else-if="result" class="mbti-result">
      <div class="mbti-result-main">
        <span class="section-kicker">Your fashion type</span>
        <p class="mbti-result-lead">你是</p>
        <h2>{{ result.name }}</h2>
        <p class="mbti-result-code">{{ result.code }}</p>
        <p class="mbti-result-desc">{{ result.description }}</p>

        <ul class="mbti-keywords">
          <li v-for="keyword in result.keywords" :key="keyword">{{ keyword }}</li>
        </ul>

        <div class="mbti-bars">
          <div v-for="bar in bars" :key="bar.id" class="mbti-bar">
            <span class="mbti-bar-title">{{ bar.title }}</span>
            <span class="mbti-bar-side" :class="{ lead: bar.leftLeads }">
              {{ bar.leftLabel }}<b v-if="bar.leftLeads">{{ bar.leftPct }}%</b>
            </span>
            <span class="mbti-bar-track" :class="{ 'from-right': !bar.leftLeads }">
              <i :style="{ width: `${bar.leadPct}%` }" />
            </span>
            <span class="mbti-bar-side right" :class="{ lead: !bar.leftLeads }">
              <b v-if="!bar.leftLeads">{{ bar.rightPct }}%</b>{{ bar.rightLabel }}
            </span>
          </div>
        </div>

        <div class="mbti-actions">
          <button class="primary-button" @click="saveImage">
            <Download :size="16" />儲存我的穿搭人格
          </button>
          <button
            class="secondary-button"
            :disabled="savingPreference || alreadySaved"
            @click="saveToPreferences"
          >
            <component :is="alreadySaved ? Check : SlidersHorizontal" :size="16" />
            {{ alreadySaved ? '已存入我的偏好' : '加入我的偏好' }}
          </button>
          <button class="mbti-text-button" @click="retake">
            <RotateCcw :size="14" />重新測驗
          </button>
        </div>

        <div v-if="confirmingRetake" class="mbti-confirm">
          <p>重新測驗會覆蓋目前這組結果，確定嗎？</p>
          <div>
            <button class="secondary-button" @click="confirmingRetake = false">取消</button>
            <button class="primary-button" @click="retake">確定重測</button>
          </div>
        </div>
      </div>

      <aside class="mbti-card-preview">
        <canvas ref="cardCanvas" width="1080" height="1350" aria-label="Fashion MBTI 分享圖" />
      </aside>
    </div>
  </section>
</template>
