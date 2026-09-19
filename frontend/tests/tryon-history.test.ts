import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Human3DJob, TryOnJob } from '../src/types.ts'
import {
  human3DJobForTryOn,
  normalizeTryOnHistory,
  parseTryOnHistory,
  transitionedToTerminal,
  upsertHuman3DJob,
} from '../src/utils/tryOnHistory.ts'

const NOW = Date.parse('2026-09-19T12:00:00Z')

function tryOnJob(id: string, overrides: Partial<TryOnJob> = {}): TryOnJob {
  return {
    id,
    status: 'succeeded',
    reference_types: ['upper'],
    error: null,
    result_url: `/api/try-on/jobs/${id}/result`,
    created_at: '2026-09-19T10:00:00Z',
    updated_at: '2026-09-19T10:05:00Z',
    expires_at: '2026-09-20T10:00:00Z',
    ...overrides,
  }
}

function human3DJob(
  id: string,
  tryOnJobId: string,
  overrides: Partial<Human3DJob> = {},
): Human3DJob {
  return {
    id,
    try_on_job_id: tryOnJobId,
    status: 'queued',
    error: null,
    artifact_type: null,
    artifact_format: null,
    result_url: null,
    created_at: '2026-09-19T10:10:00Z',
    updated_at: '2026-09-19T10:10:00Z',
    expires_at: '2026-09-20T10:10:00Z',
    ...overrides,
  }
}

test('v2 try-on history migrates to v3 without losing jobs or selection', () => {
  const first = tryOnJob('tryon-1')
  const second = tryOnJob('tryon-2', { created_at: '2026-09-19T11:00:00Z' })
  const restored = parseTryOnHistory(JSON.stringify({
    version: 2,
    selectedJobId: first.id,
    jobs: [first, second],
  }), NOW)

  assert.equal(restored?.version, 3)
  assert.equal(restored?.selectedJobId, first.id)
  assert.deepEqual(restored?.jobs.map((job) => job.id), [second.id, first.id])
  assert.deepEqual(restored?.human3DJobs, [])
})

test('normalization keeps the latest 3D job per retained try-on job', () => {
  const retained = tryOnJob('tryon-retained')
  const expired = tryOnJob('tryon-expired', { expires_at: '2026-09-19T11:59:00Z' })
  const older = human3DJob('3d-old', retained.id)
  const latest = human3DJob('3d-latest', retained.id, {
    status: 'running',
    updated_at: '2026-09-19T11:30:00Z',
  })
  const orphan = human3DJob('3d-orphan', expired.id)

  const normalized = normalizeTryOnHistory(
    [retained, expired],
    [older, latest, orphan],
    retained.id,
    NOW,
  )

  assert.deepEqual(normalized.jobs.map((job) => job.id), [retained.id])
  assert.deepEqual(normalized.human3DJobs.map((job) => job.id), [latest.id])
  assert.equal(human3DJobForTryOn(normalized.human3DJobs, retained.id)?.id, latest.id)
})

test('retry replaces only the matching try-on 3D job', () => {
  const first = human3DJob('3d-first', 'tryon-1', { status: 'failed' })
  const other = human3DJob('3d-other', 'tryon-2')
  const retry = human3DJob('3d-retry', 'tryon-1')

  const updated = upsertHuman3DJob([first, other], retry)

  assert.deepEqual(updated.map((job) => job.id), [retry.id, other.id])
})

test('terminal transitions notify only once', () => {
  assert.equal(transitionedToTerminal('running', 'succeeded'), true)
  assert.equal(transitionedToTerminal('queued', 'failed'), true)
  assert.equal(transitionedToTerminal(null, 'succeeded'), true)
  assert.equal(transitionedToTerminal('succeeded', 'succeeded'), false)
  assert.equal(transitionedToTerminal('failed', 'failed'), false)
  assert.equal(transitionedToTerminal('succeeded', 'failed'), false)
})
