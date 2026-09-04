export type GarmentZone = 'upper_body' | 'lower_body' | 'one_piece' | 'accessory' | 'other'
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
