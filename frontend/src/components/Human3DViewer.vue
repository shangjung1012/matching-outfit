<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AlertCircle, LoaderCircle, RefreshCw, RotateCcw } from 'lucide-vue-next'

const props = defineProps<{ src: string }>()

const host = ref<HTMLElement | null>(null)
const loading = ref(true)
const progress = ref(0)
const error = ref('')
let viewer: any = null
let artifactUrl = ''
let abortController: AbortController | null = null
let generation = 0

async function disposeViewer() {
  const current = viewer
  viewer = null
  if (current) {
    try {
      await current.dispose()
    } catch {
      // The library may try to detach a caller-owned root after releasing WebGL.
    }
  }
  if (artifactUrl) URL.revokeObjectURL(artifactUrl)
  artifactUrl = ''
  if (host.value) host.value.replaceChildren()
}

async function load() {
  const currentGeneration = ++generation
  abortController?.abort()
  abortController = new AbortController()
  await disposeViewer()
  loading.value = true
  progress.value = 0
  error.value = ''
  try {
    if (!host.value) return
    const probe = document.createElement('canvas')
    if (!probe.getContext('webgl2') && !probe.getContext('webgl')) {
      throw new Error('此瀏覽器或裝置目前無法使用 WebGL。')
    }
    const response = await fetch(props.src, { signal: abortController.signal })
    if (!response.ok) throw new Error(`3D 檔案下載失敗（${response.status}）`)
    const blob = await response.blob()
    if (currentGeneration !== generation) return
    artifactUrl = URL.createObjectURL(blob)
    const GaussianSplats3D = await import('@mkkellogg/gaussian-splats-3d')
    if (currentGeneration !== generation || !host.value) return
    viewer = new GaussianSplats3D.Viewer({
      rootElement: host.value,
      cameraUp: [0, 1, 0],
      initialCameraPosition: [0, 0.2, 3.2],
      initialCameraLookAt: [0, 0.15, 0],
      sharedMemoryForWorkers: false,
      gpuAcceleratedSort: true,
      halfPrecisionCovariancesOnGPU: true,
      freeIntermediateSplatData: true,
      renderMode: GaussianSplats3D.RenderMode.OnChange,
    })
    await viewer.addSplatScene(artifactUrl, {
      format: GaussianSplats3D.SceneFormat.Ply,
      splatAlphaRemovalThreshold: 5,
      showLoadingUI: false,
      progressiveLoad: true,
      onProgress: (percentage: number) => {
        progress.value = Math.max(0, Math.min(100, Math.round(percentage)))
      },
    })
    if (currentGeneration !== generation) return
    viewer.start()
    loading.value = false
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === 'AbortError') return
    loading.value = false
    error.value = reason instanceof Error ? reason.message : '無法開啟 3D View。'
  }
}

function resetCamera() {
  if (!viewer?.camera || !viewer?.controls) return
  viewer.camera.position.copy(viewer.initialCameraPosition)
  viewer.camera.up.copy(viewer.cameraUp).normalize()
  viewer.controls.target.copy(viewer.initialCameraLookAt)
  viewer.camera.lookAt(viewer.initialCameraLookAt)
  viewer.controls.update()
  viewer.forceRenderNextFrame?.()
}

watch(() => props.src, load)
onMounted(load)
onBeforeUnmount(() => {
  generation += 1
  abortController?.abort()
  void disposeViewer()
})
</script>

<template>
  <section class="human3d-viewer" aria-label="互動式 3D 人物檢視器">
    <div ref="host" class="human3d-canvas" />
    <div v-if="loading" class="human3d-overlay" role="status" aria-live="polite">
      <LoaderCircle :size="32" class="spinning" />
      <strong>正在載入 3D View…</strong>
      <span v-if="progress">{{ progress }}%</span>
    </div>
    <div v-else-if="error" class="human3d-overlay error" role="alert">
      <AlertCircle :size="30" />
      <strong>3D View 載入失敗</strong>
      <p>{{ error }}</p>
      <button type="button" class="secondary-button" @click="load">
        <RefreshCw :size="16" />重新載入
      </button>
    </div>
    <button
      v-if="!loading && !error"
      type="button"
      class="human3d-reset"
      aria-label="重設 3D 相機視角"
      @click="resetCamera"
    >
      <RotateCcw :size="16" />重設視角
    </button>
    <p v-if="!error" class="human3d-help">拖曳旋轉 · 滾輪或雙指縮放</p>
  </section>
</template>
