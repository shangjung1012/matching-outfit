import type {
  Audience,
  CatalogItem,
  CatalogSemanticSearchResponse,
  ClarificationResponse,
  ClothResult,
  GarmentZone,
  PlannerGarmentZone,
  HardRules,
  PreferenceBundle,
  QueryDraft,
  RequirementSummary,
  StylePreference,
  StylePreferenceCreate,
  StylePreferenceProposal,
  TryOnCapabilities,
  TryOnJob,
  TryOnReferenceType,
  QueryPlanResponse,
  RecommendationResponse,
  FashionArticleAdmin,
  FashionArticleCollectResponse,
  FashionArticleAutoUpdateResponse,
  FashionKnowledgeSource,
  StylingGuide,
  FashionIntent,
  FavoriteCollection,
  FavoriteItemsMutationResponse,
} from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  const text = await response.text()
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      // non-JSON body (proxy error page, empty 404, etc.)
    }
  }
  if (!response.ok) {
    const detail = (payload as { detail?: string } | null)?.detail
    throw new Error(detail ?? `Request failed: ${response.status} ${response.statusText}`.trim())
  }
  return payload as T
}

function json(method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}

function withSignal(init: RequestInit, signal?: AbortSignal): RequestInit {
  return signal ? { ...init, signal } : init
}

export function createQueryPlan(
  userInput: string,
  userKey: string,
  requirements: RequirementSummary | null,
  audience?: Audience,
  searchGarmentZones?: PlannerGarmentZone[] | null,
  signal?: AbortSignal,
) {
  return request<QueryPlanResponse>('/api/query-plans', withSignal(json('POST', {
    user_input: userInput,
    user_key: userKey,
    audience: audience || null,
    requirements,
    search_garment_zones: searchGarmentZones || null,
    include_debug: true,
  }), signal))
}

export function clarifyRequirements(
  messages: Array<{ role: 'agent' | 'user'; text: string }>,
  userKey: string,
  previousRequirements: RequirementSummary | null,
  audience?: Audience,
  signal?: AbortSignal,
) {
  return request<ClarificationResponse>('/api/query-plans/clarify', withSignal(json('POST', {
    messages,
    user_key: userKey,
    audience: audience || null,
    previous_requirements: previousRequirements,
  }), signal))
}

export function refineQueryPlan(
  userInput: string,
  userKey: string,
  existingQueries: QueryDraft[],
  originalInput: string,
  requirements: RequirementSummary | null,
  fashionIntent: FashionIntent | null,
  audience?: Audience,
  searchGarmentZones?: PlannerGarmentZone[] | null,
  signal?: AbortSignal,
) {
  return request<QueryPlanResponse>('/api/query-plans/refine', withSignal(json('POST', {
    user_input: userInput,
    user_key: userKey,
    existing_queries: existingQueries,
    original_input: originalInput,
    audience: audience || null,
    requirements,
    fashion_intent: fashionIntent,
    search_garment_zones: searchGarmentZones || null,
    include_debug: true,
  }), signal))
}

export function getRecommendations(
  queries: QueryDraft[],
  userKey: string,
  userInput: string,
  requirements: RequirementSummary | null,
  stylingGuide: StylingGuide | null,
  audience?: Audience,
  signal?: AbortSignal,
  fashionIntent?: FashionIntent | null,
  referenceImage?: File | null,
  referenceType?: 'upper_body' | 'lower_body' | null,
) {
  const payload = {
    queries,
    top_k: 10,
    user_key: userKey,
    user_input: userInput,
    audience: audience || null,
    requirements,
    styling_guide: stylingGuide,
    shortlist_count: 30,
    fashion_intent: fashionIntent || null,
    final_count: 10,
    use_aesthetic_review: true,
    include_debug: true,
  }
  if (referenceImage && referenceType) {
    const form = new FormData()
    form.append('payload', JSON.stringify(payload))
    form.append('reference_image', referenceImage)
    form.append('reference_type', referenceType)
    return request<RecommendationResponse>('/api/recommendations', withSignal({
      method: 'POST',
      body: form,
    }, signal))
  }
  return request<RecommendationResponse>('/api/recommendations', withSignal(json('POST', payload), signal))
}

export function getSimilarClothes(image: File, garmentType: GarmentZone, results = 24) {
  const form = new FormData()
  form.append('image', image)
  const params = new URLSearchParams({ type: garmentType, results: String(results) })
  return request<ClothResult[]>(`/api/similarity_image?${params}`, {
    method: 'POST',
    body: form,
  })
}

const prefBase = (userKey: string) => `/api/preferences/${encodeURIComponent(userKey)}`

// ---- Learn soft preferences from a liked outfit ----

export function proposeSoftFromOutfit(
  userKey: string,
  outfitItemIds: number[][],
  userRequest: string,
  requirements: RequirementSummary | null,
) {
  return request<StylePreferenceProposal>(`${prefBase(userKey)}/soft/from-outfit`, json('POST', {
    user_key: userKey,
    user_request: userRequest,
    outfit_item_ids: outfitItemIds,
    requirements,
  }))
}

export function confirmSoftPreferences(userKey: string, rows: StylePreferenceCreate[]) {
  return request<{ status: string; created: number; updated: number }>(
    `${prefBase(userKey)}/soft/confirm`,
    json('POST', { user_key: userKey, rows }),
  )
}

export function proposeSoftFromItem(userKey: string, itemId: number) {
  return request<StylePreferenceProposal>(
    `${prefBase(userKey)}/soft/from-item`,
    json('POST', { item_id: itemId }),
  )
}

export function getFavorites(userKey: string) {
  return request<FavoriteCollection>(
    `/api/favorites/${encodeURIComponent(userKey)}`,
  )
}

export function updateFavoriteItems(
  userKey: string,
  itemIds: number[],
  favorited: boolean,
) {
  return request<FavoriteItemsMutationResponse>(
    `/api/favorites/${encodeURIComponent(userKey)}/items`,
    json('PUT', { item_ids: itemIds, favorited }),
  )
}

export function updateFavoriteOutfit(
  userKey: string,
  itemIds: number[],
  favorited: boolean,
) {
  return request<FavoriteCollection>(
    `/api/favorites/${encodeURIComponent(userKey)}/outfits`,
    json('PUT', { item_ids: itemIds, favorited }),
  )
}

export function getCatalog(zone = '') {
  const params = new URLSearchParams({ limit: '100' })
  if (zone) params.set('zone', zone)
  return request<{ items: CatalogItem[]; total: number }>(`/api/catalog?${params}`)
}

export function searchCatalogByEmbedding(
  query: string,
  userKey: string,
  zone = '',
  limit = 60,
) {
  return request<CatalogSemanticSearchResponse>('/api/catalog/semantic-search', json('POST', {
    query,
    user_key: userKey,
    zone: zone || null,
    limit,
  }))
}

// ---- Preference settings page ----

export function getPreferenceBundle(userKey: string) {
  return request<PreferenceBundle>(prefBase(userKey))
}

export function saveHardRules(userKey: string, hard: HardRules) {
  return request<HardRules>(
    `${prefBase(userKey)}/hard`,
    json('PUT', { ...hard, user_key: userKey }),
  )
}

export function addStylePreference(userKey: string, row: StylePreferenceCreate) {
  return request<StylePreference>(`${prefBase(userKey)}/soft`, json('POST', row))
}

export function patchStylePreference(
  userKey: string,
  id: number,
  patch: { is_active?: boolean; preference_text?: string },
) {
  return request<StylePreference>(`${prefBase(userKey)}/soft/${id}`, json('PATCH', patch))
}

export function deleteStylePreference(userKey: string, id: number) {
  return request<void>(`${prefBase(userKey)}/soft/${id}`, json('DELETE'))
}

export function getTryOnCapabilities() {
  return request<TryOnCapabilities>('/api/try-on/capabilities')
}

export function createTryOnJob(
  personImage: File,
  references: Partial<Record<TryOnReferenceType, File>>,
  userKey: string,
) {
  const form = new FormData()
  form.append('person_image', personImage)
  for (const referenceType of ['upper', 'lower', 'overall', 'shoe', 'bag'] as const) {
    const file = references[referenceType]
    if (file) form.append(`${referenceType}_image`, file)
  }
  form.append('user_key', userKey)
  return request<TryOnJob>('/api/try-on/jobs', { method: 'POST', body: form })
}

export function getTryOnJob(jobId: string) {
  return request<TryOnJob>(`/api/try-on/jobs/${encodeURIComponent(jobId)}`)
}

export function getFashionArticles(search = '') {
  const params = new URLSearchParams({ limit: '100' })
  if (search.trim()) params.set('search', search.trim())
  return request<{ items: FashionArticleAdmin[]; total: number }>(
    `/api/fashion-knowledge/articles?${params}`,
  )
}

export function collectFashionArticles(urls: string[], rawText = '', forceRefresh = false) {
  return request<FashionArticleCollectResponse>(
    '/api/fashion-knowledge/articles/collect',
    json('POST', { urls, raw_text: rawText, force_refresh: forceRefresh, download_images: false, max_images: 4 }),
  )
}

export function getFashionKnowledgeSources() {
  return request<FashionKnowledgeSource[]>('/api/fashion-knowledge/sources')
}

export function autoUpdateFashionArticles(
  sourceKeys: string[], perSourceLimit: number, pageLimit: number,
) {
  return request<FashionArticleAutoUpdateResponse>(
    '/api/fashion-knowledge/articles/auto-update',
    json('POST', {
      source_keys: sourceKeys,
      per_source_limit: perSourceLimit,
      page_limit: Math.max(0, pageLimit),
      max_articles: Math.min(12, Math.max(1, sourceKeys.length * perSourceLimit)),
    }),
  )
}

export function setFashionObservationActive(id: number, isActive: boolean) {
  return request(`/api/fashion-knowledge/observations/${id}`, json('PATCH', {
    is_active: isActive,
  }))
}

export function deleteFashionArticle(id: number) {
  return request<void>(`/api/fashion-knowledge/articles/${id}`, json('DELETE'))
}
