import type {
  Audience,
  CatalogItem,
  PreferenceProposal,
  QueryDraft,
  TryOnCapabilities,
  TryOnClothType,
  TryOnJob,
  QueryPlanResponse,
  RecommendationResponse,
  UserPreference,
} from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.detail ?? `Request failed: ${response.status}`)
  return payload as T
}

function json(method: 'POST' | 'PUT', body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export function createQueryPlan(userInput: string, userKey: string, audience?: Audience) {
  return request<QueryPlanResponse>('/api/query-plans', json('POST', {
    user_input: userInput,
    user_key: userKey,
    audience: audience || null,
  }))
}

export function refineQueryPlan(
  userInput: string,
  userKey: string,
  existingQueries: QueryDraft[],
  originalInput: string,
  audience?: Audience,
) {
  return request<QueryPlanResponse>('/api/query-plans/refine', json('POST', {
    user_input: userInput,
    user_key: userKey,
    existing_queries: existingQueries,
    original_input: originalInput,
    audience: audience || null,
  }))
}

export function getRecommendations(
  queries: QueryDraft[],
  userKey: string,
  userInput: string,
  audience?: Audience,
) {
  return request<RecommendationResponse>('/api/recommendations', json('POST', {
    queries,
    top_k: 25,
    user_key: userKey,
    user_input: userInput,
    audience: audience || null,
    shortlist_count: 15,
    final_count: 5,
    use_aesthetic_review: true,
  }))
}

export function getPreferenceProposal(userKey: string, likedItemIds: number[]) {
  return request<PreferenceProposal>('/api/preferences/proposals', json('POST', {
    user_key: userKey,
    liked_item_ids: likedItemIds,
  }))
}

export function confirmPreferenceProposal(userKey: string, proposal: PreferenceProposal) {
  return request<{ status: string }>('/api/preferences/confirm', json('POST', {
    user_key: userKey,
    ...proposal,
  }))
}

export function getCatalog(zone = '', search = '') {
  const params = new URLSearchParams({ limit: '100' })
  if (zone) params.set('zone', zone)
  if (search) params.set('search', search)
  return request<{ items: CatalogItem[]; total: number }>(`/api/catalog?${params}`)
}

export function getUserPreference(userKey: string) {
  return request<UserPreference>(`/api/preferences/${encodeURIComponent(userKey)}`)
}

export function saveUserPreference(userKey: string, preference: UserPreference) {
  return request<UserPreference>(
    `/api/preferences/${encodeURIComponent(userKey)}`,
    json('PUT', preference),
  )
}

export function getTryOnCapabilities() {
  return request<TryOnCapabilities>('/api/try-on/capabilities')
}

export function createTryOnJob(
  personImage: File,
  clothImage: File,
  clothType: TryOnClothType,
  userKey: string,
) {
  const form = new FormData()
  form.append('person_image', personImage)
  form.append('cloth_image', clothImage)
  form.append('cloth_type', clothType)
  form.append('user_key', userKey)
  return request<TryOnJob>('/api/try-on/jobs', { method: 'POST', body: form })
}

export function getTryOnJob(jobId: string) {
  return request<TryOnJob>(`/api/try-on/jobs/${encodeURIComponent(jobId)}`)
}
