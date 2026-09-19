export type GarmentZone = 'upper_body' | 'lower_body' | 'one_piece' | 'accessory' | 'other'
export type PlannerGarmentZone = 'upper_body' | 'lower_body' | 'one_piece'
export type AppView =
  | 'agent'
  | 'knowledge'
  | 'similarity'
  | 'catalog'
  | 'wardrobe'
  | 'favorites'
  | 'tryon'
  | 'preferences'
  | 'mbti'
export type TryOnReferenceType = 'upper' | 'lower' | 'overall' | 'shoe' | 'bag'
export type TryOnJobStatus = 'queued' | 'running' | 'succeeded' | 'failed'
export type Human3DJobStatus = TryOnJobStatus

export type WardrobeCategory = 'upper_body' | 'lower_body' | 'shoes'

export interface WardrobeItem {
  id: number
  name: string
  category: WardrobeCategory
  image_url: string
  original_filename: string
  is_favorite: boolean
  created_at: string
}

export interface UserProfile {
  user_key: string
  do_test: boolean
}

export interface TryOnCapabilities {
  available: boolean
  reason: string | null
  supported_reference_types: TryOnReferenceType[]
  max_upload_bytes: number
  max_image_pixels: number
}

export interface TryOnJob {
  id: string
  status: TryOnJobStatus
  reference_types: TryOnReferenceType[]
  error: string | null
  result_url: string | null
  created_at: string
  updated_at: string
  expires_at: string | null
}

export interface Human3DCapabilities {
  available: boolean
  reason: string | null
  artifact_formats: string[]
}

export interface Human3DJob {
  id: string
  try_on_job_id: string
  status: Human3DJobStatus
  error: string | null
  artifact_type: string | null
  artifact_format: string | null
  result_url: string | null
  created_at: string
  updated_at: string
  expires_at: string | null
}

export interface SavedPersonPhoto {
  id: string
  userKey: string
  name: string
  blob: Blob
  mimeType: string
  size: number
  width: number
  height: number
  isDefault: boolean
  createdAt: string
  updatedAt: string
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
  direction_id?: string | null
  selected: boolean
  knowledge_observation_ids: string[]
  references: ReferenceLink[]
  preference_references?: string[]
}

export interface PairingDirection {
  id: string
  concept: string
  upper_body_focus: string
  lower_body_focus: string
  color_relationship: string
}

export interface OccasionInterpretation {
  social_context: string
  formality_target: number
  visual_impact: 'low' | 'medium' | 'high'
  practicality: 'low' | 'medium' | 'high'
}

export interface StylingConcept {
  direction_id: string
  concept_name: string
  outfit_formula: string
  upper_role: string | null
  lower_role: string | null
  one_piece_role: string | null
  visible_cues: string[]
  balance_rules: string[]
}

export interface BodyContext {
  height_band: 'short' | 'average' | 'tall' | 'unknown'
  bmi_band: 'lower' | 'middle' | 'higher' | 'unknown'
  frame_scale: 'small' | 'medium' | 'large' | 'unknown'
  shoulder_hip_balance: 'shoulder_dominant' | 'balanced' | 'hip_dominant' | 'unknown'
  midsection_fullness: 'lower' | 'moderate' | 'higher' | 'unknown'
  upper_body_volume: 'lower' | 'moderate' | 'higher' | 'unknown'
  lower_body_volume: 'lower' | 'moderate' | 'higher' | 'unknown'
  thigh_or_calf_volume: 'lower' | 'moderate' | 'higher' | 'unknown'
  leg_torso_ratio: 'shorter_legs' | 'balanced' | 'longer_legs' | 'unknown'
  fit_preference: 'fitted' | 'regular' | 'relaxed' | 'oversized' | 'mixed' | 'unknown'
  exposure_preference: 'low' | 'medium' | 'high' | 'unknown'
  areas_to_emphasize: string[]
  areas_not_to_emphasize: string[]
  access_needs: string[]
  confidence: 'low' | 'medium' | 'high'
}

export interface BodyStrategy {
  confidence: 'low' | 'medium' | 'high'
  fit_direction: string[]
  proportion_direction: string[]
  exposure_direction: string[]
  movement_and_access_direction: string[]
  soft_biases: string[]
  hard_constraints: string[]
  unknowns: string[]
}

export interface FashionIntent {
  activity_context?: {
    activity: string
    activity_present: boolean
    activity_mode: 'appearance_dominant' | 'balanced' | 'function_dominant' | 'not_applicable'
    appearance_priority: 'low' | 'medium' | 'high'
    requested_visual_identity: string
    explicit_functional_requests: string[]
    avoid_style_drift: string[]
    primary_goal: string
    secondary_goal: string
    functional_priority: 'low' | 'medium' | 'high'
    minimum_functional_requirements: string[]
    avoid_functional_drift: string[]
  }
  forbidden_style_drift?: string[]
  body_context?: BodyContext
  body_strategy?: BodyStrategy
  user_goal: string
  desired_impression: string[]
  occasion_interpretation: OccasionInterpretation
  core_aesthetic: string[]
  must_have_visual_cues: string[]
  optional_visual_cues: string[]
  avoid_concepts: string[]
  styling_principles: string[]
  concepts: StylingConcept[]
  ambiguities: string[]
  confidence: number
}

export interface StylingGuide {
  concept: string
  desired_impression: string[]
  visual_attributes: string[]
  avoid_misinterpretations: string[]
  color_direction: string[]
  silhouette_direction: string[]
  material_direction: string[]
  pattern_direction: string[]
  pairing_directions: PairingDirection[]
  styling_principles: string[]
  reviewer_checklist: string[]
}

export interface ShoeSpec {
  shoe_type: string
  shoe_color: string
  shoe_query: string
  material_appearance: string
  profile: string
}

export interface DirectionShoePlan {
  direction_id: string
  shoe_spec: ShoeSpec
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
  is_reference?: boolean
  references: ReferenceLink[]
  preference_references?: string[]
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

export type TryOnReferenceSelection =
  | { source: 'favorite'; item: CatalogItem }
  | { source: 'upload'; file: File; previewUrl: string }

export interface TryOnDraft {
  revision: number
  source: 'favorite-item' | 'favorite-outfit'
  outfitId: number | null
  candidates: Partial<Record<TryOnReferenceType, CatalogItem[]>>
  unsupportedItems: CatalogItem[]
}

export interface CatalogSemanticSearchResponse {
  query: string
  items: ClothResult[]
  total: number
  model: string
}

export interface FavoriteItem {
  item: CatalogItem
  favorited_at: string
}

export interface FavoriteOutfit {
  id: number
  favorited_at: string
  items: CatalogItem[]
}

export interface FavoriteCollection {
  user_key: string
  items: FavoriteItem[]
  outfits: FavoriteOutfit[]
}

export interface FavoriteItemsMutationResponse {
  user_key: string
  added: number
  removed: number
  favorite_item_ids: number[]
}

export interface OutfitRecommendation {
  id: string
  kind: 'separates' | 'one_piece'
  direction_id: string | null
  items: ClothResult[]
  score: number
  reasons: string[]
  references: ReferenceLink[]
  preference_references?: string[]
  score_breakdown: {
    fashion_clip: number
    compatibility: number
    context_fit: number
    aesthetic: number | null
  } | null
  aesthetic_review: {
    silhouette_proportion?: number | null
    pairing_coherence?: number | null
    color_material_harmony?: number | null
    constraint_compliance?: number | null
    style_drift_detected?: boolean
    style_drift_evidence?: string[]
    local_fallback_fields?: string[]
    style_identity_match?: number | null
    inner_layer_suggestion?: string
    occasion_fit: number
    color_harmony: number
    silhouette_balance: number
    material_coherence: number
    overall_aesthetic: number
    fatal_issues: string[]
    reason: string
    knowledge_observation_ids: string[]
  } | null
  shoe_suggestion?: {
    query: string
    item_id: number
    retrieval_score: number
    added_after_review: boolean
  } | null
}

export interface QueryPlanResponse {
  knowledge_observations: FashionObservationTrace[]
  knowledge_gaps: string[]
  knowledge_note: string
  queries: QueryDraft[]
  shoe_plans: DirectionShoePlan[]
  planner: string
  audience: Audience | null
  knowledge_observation_ids: string[]
  planning_note: string
  styling_guide: StylingGuide | null
  fashion_intent: FashionIntent | null
  debug: QueryPlanDebug | null
}

export interface GeneratedQueryTrace {
  garment_zone: 'upper_body' | 'lower_body' | 'one_piece'
  direction_id: string
  text: string
  rationale: string
}

export interface QueryNormalizationChange {
  direction_id: string | null
  garment_zone: GarmentZone
  before: string
  after: string
}

export interface QueryPlanDebug {
  knowledge_observations: FashionObservationTrace[]
  knowledge_used_ids: string[]
  knowledge_gaps: string[]
  knowledge_note: string
  raw_user_text: string
  requirement_summary: RequirementSummary | null
  fashion_intent: FashionIntent | null
  generated_queries_before_normalization: GeneratedQueryTrace[]
  generated_queries_after_normalization: QueryDraft[]
  shoe_plans: DirectionShoePlan[]
  normalizer_changes: QueryNormalizationChange[]
  query_warnings: string[]
  intent_fallback_used: boolean
  intent_fallback_error: string
  model: string
  prompt_version: string
  stage_timings_ms: Record<string, number>
}

export interface RequirementSummary {
  weather?: {
    status: 'available' | 'unavailable'
    location: string
    target_date: string
    location_assumed: boolean
    temperature_min_c: number | null
    temperature_max_c: number | null
    apparent_temperature_min_c: number | null
    apparent_temperature_max_c: number | null
    precipitation_probability_max: number | null
    source_url: string
    fetched_at: string
    note: string
  } | null
  location: string
  target_date: string
  outfit_budget_max: number | null
  hard_rules: HardRules | null
  defaulted_fields: string[]
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
  missing_fields: Array<Exclude<keyof RequirementSummary, 'search_brief' | 'tag_translations' | 'defaulted_fields'>>
  ready_to_plan: boolean
}

export interface RecommendationResponse {
  recommendations: OutfitRecommendation[]
  discarded_recommendations: OutfitRecommendation[]
  aesthetic_reviewed: boolean
  review_note: string
  knowledge_observation_count: number
  knowledge_sources: string[]
  knowledge_note: string
  debug: RecommendationDebug | null
}

export interface FashionObservationTrace {
  observation_id: string
  source_url: string
  source_name: string
  source_title: string
  published_at: string | null
  summary: string
  evidence: string
  audiences: string[]
  occasions: string[]
  climates: string[]
  seasons: string[]
  times_of_day: string[]
  formalities: string[]
  activities: string[]
  styles: string[]
  garments: string[]
  colors: string[]
  materials: string[]
  silhouettes: string[]
  styling_actions: string[]
  avoid_when: string[]
  signal_type: 'timeless' | 'current_trend' | 'editorial_example'
  confidence: number
}

export interface QuerySearchResult {
  query: QueryDraft
  clothes: ClothResult[]
  relaxed: boolean
}

export interface RecommendationDebug {
  search_results: QuerySearchResult[]
  ranked_candidate_count: number
  ranked_preview: OutfitRecommendation[]
  shortlist_before_review: OutfitRecommendation[]
  knowledge_observations: FashionObservationTrace[]
  aesthetic_review_attempted: boolean
  aesthetic_review_error: string
  aesthetic_review_diagnostics?: {
    candidate_count: number
    submitted_ids: string[]
    reviewed_count: number
    image_failures: { candidate_id: string; reason: string; items: { item_id: number; reason: string }[] }[]
    missing_ids: string[]
    attempts: {
      round: number
      requested_ids: string[]
      returned_ids: string[]
      invalid_ids: string[]
      duplicate_ids: string[]
      missing_ids: string[]
      error: string
    }[]
  }
  stage_timings_ms: Record<string, number>
  shoe_retrievals: {
    outfit_id: string
    original_query: string
    query: string
    requested_type: string
    requested_color: string
    candidates: ClothResult[]
    selected_item_id: number | null
  }[]
}

export interface PipelineDebugSession {
  updated_at: string
  messages: Array<{ role: 'agent' | 'user'; text: string }>
  original_input: string
  requirements: RequirementSummary | null
  fashion_intent: FashionIntent | null
  queries: QueryDraft[]
  styling_guide: StylingGuide | null
  plan_debug: QueryPlanDebug | null
  recommendation_debug: RecommendationDebug | null
  recommendations: OutfitRecommendation[]
  discarded_recommendations: OutfitRecommendation[]
  review_note: string
  knowledge_note: string
}

// ---- User preferences ----

export type PreferenceSource = 'explicit' | 'implicit'
export type PreferenceType = 'prefer' | 'avoid'

export interface HardRules {
  user_key?: string
  gender: 'female' | 'male' | 'non_binary' | 'prefer_not_to_say' | null
  age: number | null
  height_cm: number | null
  weight_kg: number | null
  price_max: number | null
  avoid_colours: string[]
  avoid_article_types: string[]
  avoid_master_categories: string[]
  notes: string | null
}

export interface StylePreferenceCreate {
  preference_text: string
  preference_type: PreferenceType
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

export interface OutfitPreferenceReaction {
  user_key: string
  user_request: string
  review_summary?: string
  outfit_item_ids: number[]
  preference_type: PreferenceType
  requirements: RequirementSummary | null
}

export interface FashionObservationAdmin {
  id: number
  observation_id: string
  summary: string
  evidence: string
  audiences: string[]
  occasions: string[]
  climates: string[]
  seasons: string[]
  times_of_day: string[]
  formalities: string[]
  activities: string[]
  styles: string[]
  garments: string[]
  colors: string[]
  materials: string[]
  silhouettes: string[]
  styling_actions: string[]
  avoid_when: string[]
  signal_type: 'timeless' | 'current_trend' | 'editorial_example'
  confidence: number
  is_active: boolean
  has_embedding: boolean
}

export interface FashionArticleAdmin {
  search_similarity?: number | null
  search_match_kind?: 'title_summary' | 'knowledge' | null
  search_match_text?: string
  id: number
  source_url: string
  source_name: string
  title: string
  author: string | null
  published_at: string | null
  collected_at: string
  language: string | null
  article_summary: string
  extraction_notes: string[]
  extraction_model: string
  observation_count: number
  active_observation_count: number
  observations: FashionObservationAdmin[]
}

export interface FashionArticleCollectResult {
  url: string
  status: 'created' | 'updated' | 'failed' | 'skipped' | 'unsupported'
  category: string
  article_id: number | null
  title: string | null
  observation_count: number
  message: string
}

export interface FashionArticleCollectResponse {
  skipped: number
  unsupported: number
  results: FashionArticleCollectResult[]
  succeeded: number
  failed: number
}

export interface FashionKnowledgeSource {
  key: string
  name: string
  index_url: string
  audience: 'men' | 'women'
}

// ---- Fashion MBTI ----

export type MbtiAxisKey = 'C' | 'S' | 'B' | 'I' | 'M' | 'O' | 'N' | 'V'
export type MbtiOptionId = 'A' | 'B' | 'C' | 'D'
export type MbtiRawScores = Record<MbtiAxisKey, number>

export interface FashionMbtiOption {
  id: MbtiOptionId
  label: string
  scores: Partial<MbtiRawScores>
  image?: string
}

export interface FashionMbtiQuestion {
  id: number
  prompt: string
  visual?: boolean
  options: FashionMbtiOption[]
}

export interface FashionMbtiAnswer {
  questionId: number
  optionId: MbtiOptionId
}

export interface FashionMbtiType {
  code: string
  name: string
  representative: { name: string }
  description: string
}

export interface FashionMbtiResult extends FashionMbtiType {
  keywords: string[]
  scores: {
    comfort: number
    style: number
    budget: number
    invest: number
    modest: number
    open: number
    neutral: number
    vivid: number
  }
  raw: MbtiRawScores
  completedAt: string
}

export interface FashionArticleAutoUpdateResponse extends FashionArticleCollectResponse {
  discovered: number
  skipped_existing: number
  candidates: string[]
  discovery_errors: Record<string, string>
}
