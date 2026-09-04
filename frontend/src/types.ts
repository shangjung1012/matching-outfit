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
export type AppView = 'agent' | 'catalog' | 'preferences'

export interface QueryDraft {
  id: string
  text: string
  garment_zone: GarmentZone
  rationale: string
  selected: boolean
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

export interface OutfitRecommendation {
  id: string
  kind: 'separates' | 'one_piece'
  items: ClothResult[]
  score: number
  reasons: string[]
  score_breakdown: {
    fashion_clip: number
    compatibility: number
    context_fit: number
    preference_adjustment: number
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
  } | null
}

export interface QueryPlanResponse {
  queries: QueryDraft[]
  planner: string
  audience: Audience | null
  knowledge_observation_ids: string[]
  planning_note: string
}

export interface RecommendationResponse {
  recommendations: OutfitRecommendation[]
  aesthetic_reviewed: boolean
  review_note: string
  knowledge_observation_count: number
  knowledge_sources: string[]
  knowledge_note: string
}

export interface PreferenceProposal {
  favorite_colors_to_add: string[]
  favorite_article_types_to_add: string[]
  explanation: string
}

export interface UserPreference {
  user_key: string
  favorite_colors: string[]
  disliked_colors: string[]
  preferred_price_min: number | null
  preferred_price_max: number | null
  preferred_styles: string[]
  preferred_categories: string[]
  preferred_usages: string[]
  favorite_article_types: string[]
  disliked_article_types: string[]
  notes: string | null
}
