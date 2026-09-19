import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canGenerateHuman3D, human3DStatusLabel } from '../src/utils/human3dUi.ts'

const succeededTryOn = {
  id: 'tryon-1', status: 'succeeded', result_url: '/result', reference_types: ['upper'],
  error: null, created_at: '', updated_at: '', expires_at: null,
} as any
const available = { available: true, reason: null, artifact_formats: ['ply'] }

test('3D generation is offered only for an available service and completed try-on', () => {
  assert.equal(canGenerateHuman3D(succeededTryOn, available, null), true)
  assert.equal(canGenerateHuman3D({ ...succeededTryOn, status: 'running' }, available, null), false)
  assert.equal(canGenerateHuman3D(succeededTryOn, { ...available, available: false }, null), false)
  assert.equal(canGenerateHuman3D(succeededTryOn, available, { status: 'running' } as any), false)
  assert.equal(canGenerateHuman3D(succeededTryOn, available, { status: 'failed' } as any), true)
})

test('3D status transitions use the required Traditional Chinese messages', () => {
  assert.equal(human3DStatusLabel({ status: 'queued' } as any), '準備建立 3D 模型…')
  assert.equal(human3DStatusLabel({ status: 'running' } as any), '正在重建人物…')
  assert.equal(human3DStatusLabel({ status: 'succeeded' } as any), '3D View 已完成')
  assert.equal(human3DStatusLabel({ status: 'failed' } as any), '3D View 建立失敗')
})
