import type {
  Human3DJob,
  TryOnJob,
  TryOnJobReference,
  TryOnJobStatus,
  TryOnReferenceType,
} from '../types'
import { TRYON_REFERENCE_TYPES } from './tryOnSelection.ts'

export const TRYON_HISTORY_LIMIT = 20

const JOB_STATUSES = ['queued', 'running', 'succeeded', 'failed'] as const

export interface TryOnHistorySnapshot {
  selectedJobId: string | null
  jobs: TryOnJob[]
  human3DJobs: Human3DJob[]
}

function hasValidDate(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value))
}

function hasValidOptionalDate(value: unknown): value is string | null {
  return value === null || hasValidDate(value)
}

export function isTryOnJob(value: unknown): value is TryOnJob {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === 'string'
    && JOB_STATUSES.includes(candidate.status as TryOnJobStatus)
    && Array.isArray(candidate.reference_types)
    && candidate.reference_types.length > 0
    && candidate.reference_types.every((type) => (
      TRYON_REFERENCE_TYPES.includes(type as TryOnReferenceType)
    ))
    && Array.isArray(candidate.references)
    && candidate.references.every(isTryOnJobReference)
    && (candidate.error === null || typeof candidate.error === 'string')
    && (candidate.result_url === null || typeof candidate.result_url === 'string')
    && hasValidDate(candidate.created_at)
    && hasValidDate(candidate.updated_at)
    && hasValidOptionalDate(candidate.expires_at)
  )
}

export function isTryOnJobReference(value: unknown): value is TryOnJobReference {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return (
    TRYON_REFERENCE_TYPES.includes(candidate.reference_type as TryOnReferenceType)
    && (candidate.source === 'catalog' || candidate.source === 'wardrobe' || candidate.source === 'upload')
    && typeof candidate.display_name === 'string'
    && (candidate.image_url === null || typeof candidate.image_url === 'string')
    && (candidate.catalog_item === null || typeof candidate.catalog_item === 'object')
    && (candidate.wardrobe_item === null || typeof candidate.wardrobe_item === 'object')
  )
}

export function isHuman3DJob(value: unknown): value is Human3DJob {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === 'string'
    && typeof candidate.try_on_job_id === 'string'
    && JOB_STATUSES.includes(candidate.status as TryOnJobStatus)
    && (candidate.error === null || typeof candidate.error === 'string')
    && (candidate.artifact_type === null || typeof candidate.artifact_type === 'string')
    && (candidate.artifact_format === null || typeof candidate.artifact_format === 'string')
    && (candidate.result_url === null || typeof candidate.result_url === 'string')
    && hasValidDate(candidate.created_at)
    && hasValidDate(candidate.updated_at)
    && hasValidOptionalDate(candidate.expires_at)
  )
}

export function jobIsExpired(
  job: Pick<TryOnJob | Human3DJob, 'expires_at'>,
  now = Date.now(),
) {
  if (!job.expires_at) return false
  const expiresAt = Date.parse(job.expires_at)
  return Number.isFinite(expiresAt) && expiresAt <= now
}

export function normalizeTryOnHistory(
  jobs: TryOnJob[],
  human3DJobs: Human3DJob[],
  selectedJobId: string | null,
): TryOnHistorySnapshot {
  const seenTryOnIds = new Set<string>()
  const normalizedJobs = jobs
    .filter((job) => {
      if (seenTryOnIds.has(job.id)) return false
      seenTryOnIds.add(job.id)
      return true
    })
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
    .slice(0, TRYON_HISTORY_LIMIT)

  const retainedTryOnIds = new Set(normalizedJobs.map((job) => job.id))
  const seenTryOn3DIds = new Set<string>()
  const normalizedHuman3DJobs = [...human3DJobs]
    .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at))
    .filter((job) => {
      if (
        !retainedTryOnIds.has(job.try_on_job_id)
        || seenTryOn3DIds.has(job.try_on_job_id)
      ) return false
      seenTryOn3DIds.add(job.try_on_job_id)
      return true
    })

  const normalizedSelectedId = normalizedJobs.some((job) => job.id === selectedJobId)
    ? selectedJobId
    : normalizedJobs[0]?.id ?? null

  return {
    selectedJobId: normalizedSelectedId,
    jobs: normalizedJobs,
    human3DJobs: normalizedHuman3DJobs,
  }
}

export function referencesForHistory(job: TryOnJob) {
  const selections: Partial<Record<TryOnReferenceType, TryOnJobReference>> = {}
  job.references.forEach((reference) => {
    if (reference.catalog_item || reference.wardrobe_item) {
      selections[reference.reference_type] = reference
    }
  })
  return selections
}

export function human3DJobForTryOn(
  jobs: Human3DJob[],
  tryOnJobId: string | null | undefined,
) {
  if (!tryOnJobId) return null
  return jobs.find((job) => job.try_on_job_id === tryOnJobId) ?? null
}

export function upsertHuman3DJob(jobs: Human3DJob[], nextJob: Human3DJob) {
  return [
    nextJob,
    ...jobs.filter((job) => job.try_on_job_id !== nextJob.try_on_job_id),
  ]
}

export function transitionedToTerminal(
  previousStatus: TryOnJobStatus | null | undefined,
  nextStatus: TryOnJobStatus,
) {
  return (
    previousStatus !== nextStatus
    && (nextStatus === 'succeeded' || nextStatus === 'failed')
    && previousStatus !== 'succeeded'
    && previousStatus !== 'failed'
  )
}
