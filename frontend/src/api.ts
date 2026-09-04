import type {
  CatalogItem,
  OutfitRecommendation,
  PreferenceProposal,
  QueryDraft,
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

export function createQueryPlan(userInput: string, userKey: string) {
  return request<{ queries: QueryDraft[] }>('/api/query-plans', json('POST', {
    user_input: userInput,
    user_key: userKey,
  }))
}

export function refineQueryPlan(userInput: string, userKey: string, existingQueries: QueryDraft[]) {
  return request<{ queries: QueryDraft[] }>('/api/query-plans/refine', json('POST', {
    user_input: userInput,
    user_key: userKey,
    existing_queries: existingQueries,
  }))
}

export function getRecommendations(queries: QueryDraft[], userKey: string) {
  return request<{ recommendations: OutfitRecommendation[] }>('/api/recommendations', json('POST', {
    queries,
    top_k: 6,
    user_key: userKey,
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
