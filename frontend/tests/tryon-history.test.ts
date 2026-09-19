import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { CatalogItem, Human3DJob, TryOnJob, WardrobeItem } from '../src/types.ts'
import {
  human3DJobForTryOn,
  normalizeTryOnHistory,
  referencesForHistory,
  transitionedToTerminal,
  upsertHuman3DJob,
} from '../src/utils/tryOnHistory.ts'

function tryOnJob(id: string, overrides: Partial<TryOnJob> = {}): TryOnJob {
  return {
    id,
    status: 'succeeded',
    reference_types: ['upper'],
    references: [],
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

test('backend history keeps expired jobs, sorts newest first, and limits to 20', () => {
  const jobs = Array.from({ length: 22 }, (_, index) => tryOnJob(`tryon-${index}`, {
    created_at: new Date(Date.UTC(2026, 8, 19, 10, index)).toISOString(),
    expires_at: index === 21 ? '2026-09-19T11:59:00Z' : '2026-09-20T10:00:00Z',
  }))
  const normalized = normalizeTryOnHistory(jobs, [], 'tryon-0')

  assert.equal(normalized.jobs.length, 20)
  assert.equal(normalized.jobs[0].id, 'tryon-21')
  assert.equal(normalized.jobs[0].expires_at, '2026-09-19T11:59:00Z')
  assert.equal(normalized.selectedJobId, 'tryon-21')
})

test('normalization keeps the latest 3D job per retained try-on job', () => {
  const retained = tryOnJob('tryon-retained')
  const expired = tryOnJob('tryon-expired', { expires_at: '2026-09-19T11:59:00Z' })
  const older = human3DJob('3d-old', retained.id)
  const latest = human3DJob('3d-latest', retained.id, {
    status: 'running',
    updated_at: '2026-09-19T11:30:00Z',
  })
  const expiredResult = human3DJob('3d-expired', expired.id)

  const normalized = normalizeTryOnHistory(
    [retained, expired],
    [older, latest, expiredResult],
    retained.id,
  )

  assert.deepEqual(normalized.jobs.map((job) => job.id), [retained.id, expired.id])
  assert.deepEqual(normalized.human3DJobs.map((job) => job.id), [latest.id, expiredResult.id])
  assert.equal(human3DJobForTryOn(normalized.human3DJobs, retained.id)?.id, latest.id)
})

test('history reapply restores current catalog and wardrobe items but skips uploads and deleted items', () => {
  const catalogItem = { id: 7 } as CatalogItem
  const wardrobeItem = { id: 9 } as WardrobeItem
  const job = tryOnJob('tryon-reapply', {
    reference_types: ['upper', 'lower', 'shoe', 'bag'],
    references: [
      { reference_type: 'upper', source: 'catalog', display_name: '上衣', image_url: '/upper.jpg', catalog_item: catalogItem, wardrobe_item: null },
      { reference_type: 'lower', source: 'wardrobe', display_name: '褲子', image_url: '/lower.jpg', catalog_item: null, wardrobe_item: wardrobeItem },
      { reference_type: 'shoe', source: 'upload', display_name: '自訂上傳', image_url: null, catalog_item: null, wardrobe_item: null },
      { reference_type: 'bag', source: 'catalog', display_name: '已刪除商品', image_url: '/bag.jpg', catalog_item: null, wardrobe_item: null },
    ],
  })

  const references = referencesForHistory(job)
  assert.equal(references.upper?.catalog_item?.id, 7)
  assert.equal(references.lower?.wardrobe_item?.id, 9)
  assert.equal(references.shoe, undefined)
  assert.equal(references.bag, undefined)
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
