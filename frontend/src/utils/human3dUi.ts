import type { Human3DCapabilities, Human3DJob, TryOnJob } from '../types'

export function canGenerateHuman3D(
  tryOnJob: TryOnJob | null,
  capabilities: Human3DCapabilities | null,
  human3DJob: Human3DJob | null,
) {
  return Boolean(
    capabilities?.available
    && tryOnJob?.status === 'succeeded'
    && tryOnJob.result_url
    && human3DJob?.status !== 'queued'
    && human3DJob?.status !== 'running',
  )
}

export function human3DStatusLabel(job: Human3DJob | null) {
  if (!job) return ''
  return {
    queued: '準備建立 3D 模型…',
    running: '正在重建人物…',
    succeeded: '3D View 已完成',
    failed: '3D View 建立失敗',
  }[job.status]
}
