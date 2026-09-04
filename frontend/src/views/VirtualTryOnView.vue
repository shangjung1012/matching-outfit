<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { AlertCircle, CheckCircle2, ImagePlus, LoaderCircle, RefreshCw, ScanFace } from 'lucide-vue-next'
import { createTryOnJob, getTryOnCapabilities, getTryOnJob } from '../api'
import type { TryOnCapabilities, TryOnClothType, TryOnJob } from '../types'

const props = defineProps<{ userKey: string }>()

const capabilities = ref<TryOnCapabilities | null>(null)
const capabilityLoading = ref(true)
const personFile = ref<File | null>(null)
const clothFile = ref<File | null>(null)
const personPreview = ref('')
const clothPreview = ref('')
const clothType = ref<TryOnClothType>('upper')
const job = ref<TryOnJob | null>(null)
const submitting = ref(false)
const error = ref('')
let pollTimer: number | undefined

const canSubmit = computed(() => (
  capabilities.value?.available
  && personFile.value
  && clothFile.value
  && !submitting.value
  && !['queued', 'running'].includes(job.value?.status ?? '')
))

const statusLabel = computed(() => {
  if (!job.value) return ''
  return {
    queued: '等待 GPU 處理',
    running: '正在產生試穿結果',
    succeeded: '試穿完成',
    failed: '試穿失敗',
  }[job.value.status]
})

function stopPolling() {
  if (pollTimer !== undefined) window.clearTimeout(pollTimer)
  pollTimer = undefined
}

function replacePreview(current: string, file: File | null) {
  if (current) URL.revokeObjectURL(current)
  return file ? URL.createObjectURL(file) : ''
}

function chooseImage(event: Event, kind: 'person' | 'cloth') {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (kind === 'person') {
    personPreview.value = replacePreview(personPreview.value, file)
    personFile.value = file
  } else {
    clothPreview.value = replacePreview(clothPreview.value, file)
    clothFile.value = file
  }
  stopPolling()
  job.value = null
  error.value = ''
}

async function loadCapabilities() {
  capabilityLoading.value = true
  error.value = ''
  try {
    capabilities.value = await getTryOnCapabilities()
  } catch (reason) {
    capabilities.value = null
    error.value = reason instanceof Error ? reason.message : '無法檢查 CatVTON 狀態'
  } finally {
    capabilityLoading.value = false
  }
}

async function pollJob() {
  if (!job.value) return
  try {
    job.value = await getTryOnJob(job.value.id)
    error.value = ''
    if (job.value.status === 'queued' || job.value.status === 'running') {
      pollTimer = window.setTimeout(pollJob, 2000)
    } else if (job.value.status === 'failed') {
      error.value = job.value.error || '試穿工作失敗'
    }
  } catch (reason) {
    const message = reason instanceof Error ? reason.message : '無法取得試穿進度'
    error.value = `與 CatVTON 的連線暫時中斷，將自動重試：${message}`
    pollTimer = window.setTimeout(pollJob, 5000)
  }
}

async function submit() {
  if (!canSubmit.value || !personFile.value || !clothFile.value) return
  stopPolling()
  submitting.value = true
  error.value = ''
  job.value = null
  try {
    job.value = await createTryOnJob(
      personFile.value,
      clothFile.value,
      clothType.value,
      props.userKey,
    )
    pollTimer = window.setTimeout(pollJob, 2000)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '無法建立試穿工作'
    await loadCapabilities()
  } finally {
    submitting.value = false
  }
}

onMounted(loadCapabilities)
onBeforeUnmount(() => {
  stopPolling()
  if (personPreview.value) URL.revokeObjectURL(personPreview.value)
  if (clothPreview.value) URL.revokeObjectURL(clothPreview.value)
})
</script>

<template>
  <section class="page-view tryon-view">
    <header class="view-heading">
      <div>
        <span class="section-kicker">Virtual try-on</span>
        <h2>虛擬試穿</h2>
        <p>上傳全身人物照與單件衣服圖片，使用 CatVTON 產生試穿預覽。</p>
      </div>
      <button class="secondary-button" :disabled="capabilityLoading" @click="loadCapabilities">
        <RefreshCw :size="16" :class="{ spinning: capabilityLoading }" />重新檢查服務
      </button>
    </header>

    <div
      v-if="!capabilityLoading && !capabilities?.available"
      class="tryon-service-banner unavailable"
      role="status"
    >
      <AlertCircle :size="19" />
      <div><strong>CatVTON 尚未連線</strong><p>{{ capabilities?.reason || 'GPU 推論服務目前無法使用' }}</p></div>
    </div>
    <div v-else-if="capabilities?.available" class="tryon-service-banner available" role="status">
      <CheckCircle2 :size="19" />
      <div><strong>CatVTON 已就緒</strong><p>圖片會在工作結束後刪除，結果保留 24 小時。</p></div>
    </div>

    <div class="tryon-layout">
      <section class="tryon-form-card">
        <div class="tryon-upload-grid">
          <label class="tryon-upload">
            <span>1 · 人物照片</span>
            <div class="tryon-preview">
              <img v-if="personPreview" :src="personPreview" alt="人物照片預覽" />
              <div v-else><ImagePlus :size="30" /><strong>選擇人物照片</strong><small>建議使用正面全身照</small></div>
            </div>
            <input type="file" accept="image/jpeg,image/png,image/webp" @change="chooseImage($event, 'person')" />
          </label>

          <label class="tryon-upload">
            <span>2 · 衣服圖片</span>
            <div class="tryon-preview">
              <img v-if="clothPreview" :src="clothPreview" alt="衣服圖片預覽" />
              <div v-else><ImagePlus :size="30" /><strong>選擇衣服圖片</strong><small>建議使用乾淨背景商品照</small></div>
            </div>
            <input type="file" accept="image/jpeg,image/png,image/webp" @change="chooseImage($event, 'cloth')" />
          </label>
        </div>

        <fieldset class="tryon-type-field">
          <legend>3 · 試穿類型</legend>
          <div class="segmented-control">
            <button type="button" :class="{ active: clothType === 'upper' }" @click="clothType = 'upper'">上身</button>
            <button type="button" :class="{ active: clothType === 'lower' }" @click="clothType = 'lower'">下身</button>
            <button type="button" :class="{ active: clothType === 'overall' }" @click="clothType = 'overall'">洋裝／連身</button>
          </div>
        </fieldset>

        <p v-if="error" class="error-banner">{{ error }}</p>
        <button class="primary-button tryon-submit" :disabled="!canSubmit" @click="submit">
          <LoaderCircle v-if="submitting" :size="17" class="spinning" />
          <ScanFace v-else :size="17" />
          {{ submitting ? '建立工作中…' : '開始虛擬試穿' }}
        </button>
        <p class="tryon-limit">每張圖片上限 {{ Math.round((capabilities?.max_upload_bytes || 10485760) / 1048576) }} MiB</p>
      </section>

      <section class="tryon-result-card">
        <div v-if="job?.status === 'succeeded' && job.result_url" class="tryon-result">
          <img :src="job.result_url" alt="CatVTON 虛擬試穿結果" />
          <div><CheckCircle2 :size="17" /><strong>{{ statusLabel }}</strong></div>
        </div>
        <div v-else class="tryon-result-placeholder" :class="{ processing: job?.status === 'queued' || job?.status === 'running' }">
          <LoaderCircle v-if="job?.status === 'queued' || job?.status === 'running'" :size="36" class="spinning" />
          <ScanFace v-else :size="42" />
          <h3>{{ statusLabel || '試穿結果會顯示在這裡' }}</h3>
          <p v-if="job?.status === 'queued'">GPU 同一時間處理一個工作，請保留此頁面。</p>
          <p v-else-if="job?.status === 'running'">生成通常需要數十秒，請勿重複送出。</p>
          <p v-else>準備好兩張圖片並連接 GPU 服務後即可開始。</p>
        </div>
      </section>
    </div>

    <p class="tryon-attribution">
      Powered by CatVTON · CC BY-NC-SA 4.0 · 僅供非商業用途
    </p>
  </section>
</template>
