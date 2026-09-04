export type GarmentZone = 'upper_body' | 'lower_body' | 'one_piece' | 'accessory' | 'other'
export type AppView = 'agent' | 'catalog' | 'tryon' | 'preferences'
export type TryOnClothType = 'upper' | 'lower' | 'overall'
export type TryOnJobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface TryOnCapabilities {
  available: boolean
  reason: string | null
  supported_cloth_types: TryOnClothType[]
  max_upload_bytes: number
}

export interface TryOnJob {
  id: string
  status: TryOnJobStatus
  cloth_type: TryOnClothType
  error: string | null
  result_url: string | null
  created_at: string
  updated_at: string
  expires_at: string | null
}
export type Audience = 'men' | 'women' | 'unisex'

export interface ReferenceLink {
  title: string
  url: string
}

export interface QueryDraft {
  id: string
  text: string
  garment_zone: GarmentZone
  rationale: string
  selected: boolean
  knowledge_observation_ids: string[]
  references: ReferenceLink[]
}

export interface ClothResult {
  id: number
  source_item_id?: number | null
  product_display_name: string
  garment_zone: GarmentZone
  image_url: string
  price: number
  original_price: number | null
  discounted_price: number | null
  currency: string
  brand_name: string | null
  age_group: string | null
  gender: string | null
  usage: string | null
  base_colour: string | null
  article_type: string | null
  similarity: number
  references: ReferenceLink[]
}

export interface CatalogItem {
  id: number
  source_item_id: number | null
  product_display_name: string
  garment_zone: GarmentZone
  image_url: string
  price: number
  original_price: number | null
  discounted_price: number | null
  currency: string
  brand_name: string | null
  age_group: string | null
  gender: string | null
  master_category: string | null
  sub_category: string | null
  article_type: string | null
  base_colour: string | null
  season: string | null
  year: number | null
  usage: string | null
  has_embedding: boolean
}

export interface CatalogSemanticSearchResponse {
  query: string
  items: ClothResult[]
  total: number
  model: string
}

export interface OutfitRecommendation {
  id: string
  kind: 'separates' | 'one_piece'
  items: ClothResult[]
  score: number
  reasons: string[]
  references: ReferenceLink[]
  score_breakdown: {
    fashion_clip: number
    compatibility: number
    context_fit: number
    aesthetic: number | null
  } | null
  aesthetic_review: {
    occasion_fit: number
    color_harmony: number
    silhouette_balance: number
    material_coherence: number
    overall_aesthetic: number
    fatal_issues: string[]
    reason: string
    knowledge_observation_ids: string[]
  } | null
}

export interface QueryPlanResponse {
  queries: QueryDraft[]
  planner: string
  audience: Audience | null
  knowledge_observation_ids: string[]
  planning_note: string
}

export interface RequirementSummary {
  occasions: string[]
  seasons: string[]
  times_of_day: string[]
  climates: string[]
  formalities: string[]
  activities: string[]
  styles: string[]
  special_requirements: string[]
  additional_notes: string
  search_brief: string
  tag_translations: Record<string, string>
}

export interface ClarificationResponse {
  reply: string
  requirements: RequirementSummary
  missing_fields: Array<Exclude<keyof RequirementSummary, 'search_brief' | 'tag_translations'>>
  ready_to_plan: boolean
}

export interface RecommendationResponse {
  recommendations: OutfitRecommendation[]
  aesthetic_reviewed: boolean
  review_note: string
  knowledge_observation_count: number
  knowledge_sources: string[]
  knowledge_note: string
}

// ---- User preferences ----

export type PreferenceSource = 'explicit' | 'implicit'

export interface HardRules {
  user_key?: string
  gender: 'female' | 'male' | 'non_binary' | 'prefer_not_to_say' | null
  age: number | null
  height_cm: number | null
  weight_kg: number | null
  price_min: number | null
  price_max: number | null
  avoid_colours: string[]
  avoid_article_types: string[]
  avoid_master_categories: string[]
  notes: string | null
}

export interface StylePreferenceCreate {
  preference_text: string
  source: PreferenceSource
  origin_item_ids: string[]
  occasions: string[]
  seasons: string[]
  times_of_day: string[]
  climates: string[]
  formalities: string[]
  activities: string[]
  styles: string[]
}

export interface StylePreference extends StylePreferenceCreate {
  id: number
  user_key: string
  is_active: boolean
  confirmed_at: string | null
  created_at: string | null
}

export interface PreferenceBundle {
  hard: HardRules
  soft: StylePreference[]
}

export interface StylePreferenceProposal {
  proposals: StylePreferenceCreate[]
  explanation: string
}
