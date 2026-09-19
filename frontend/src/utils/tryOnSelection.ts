import type {
  CatalogItem,
  GarmentZone,
  TryOnDraft,
  TryOnReferenceType,
  WardrobeCategory,
  WardrobeItem,
} from '../types'

const SHOE_WORDS = /\b(shoe|shoes|boot|boots|sneaker|sneakers|sandal|sandals|pump|pumps|ballerina|ballerinas|slipper|slippers|heel|heels|footwear|wedge|wedges|bootie|booties|flip flop|flip flops)\b/i
const BAG_WORDS = /\b(bag|bags|handbag|handbags|backpack|backpacks|purse|purses|tote|totes|clutch|clutches)\b/i

export const TRYON_REFERENCE_TYPES = [
  'upper',
  'lower',
  'overall',
  'shoe',
  'bag',
] as const satisfies readonly TryOnReferenceType[]

export const TRYON_REFERENCE_LABELS: Record<TryOnReferenceType, string> = {
  upper: '上身',
  lower: '下身',
  overall: '洋裝／連身',
  shoe: '鞋子',
  bag: '包包',
}

export const TRYON_REFERENCE_ZONES: Record<TryOnReferenceType, GarmentZone> = {
  upper: 'upper_body',
  lower: 'lower_body',
  overall: 'one_piece',
  shoe: 'accessory',
  bag: 'accessory',
}

export const TRYON_WARDROBE_CATEGORIES: Record<TryOnReferenceType, WardrobeCategory> = {
  upper: 'upper_body',
  lower: 'lower_body',
  overall: 'one_piece',
  shoe: 'shoes',
  bag: 'bags',
}

export function referenceTypeForWardrobeItem(item: WardrobeItem): TryOnReferenceType {
  return {
    upper_body: 'upper',
    lower_body: 'lower',
    one_piece: 'overall',
    shoes: 'shoe',
    bags: 'bag',
  }[item.category] as TryOnReferenceType
}

export function referenceTypeForCatalogItem(item: CatalogItem): TryOnReferenceType | null {
  if (item.garment_zone === 'upper_body') return 'upper'
  if (item.garment_zone === 'lower_body') return 'lower'
  if (item.garment_zone === 'one_piece') return 'overall'
  if (item.garment_zone !== 'accessory') return null

  // Accessories are only safe to route when the catalog taxonomy identifies
  // them. Product names can contain styling terms such as "shoe bag" that do
  // not describe the actual item type.
  const category = [item.sub_category, item.article_type].filter(Boolean).join(' ')
  if (BAG_WORDS.test(category)) return 'bag'
  if (SHOE_WORDS.test(category)) return 'shoe'
  return null
}

export function createTryOnDraft(
  items: CatalogItem[],
  source: TryOnDraft['source'],
  outfitId: number | null = null,
): TryOnDraft {
  const candidates: TryOnDraft['candidates'] = {}
  const unsupportedItems: CatalogItem[] = []
  for (const item of items) {
    const referenceType = referenceTypeForCatalogItem(item)
    if (!referenceType) {
      unsupportedItems.push(item)
      continue
    }
    candidates[referenceType] = [...(candidates[referenceType] ?? []), item]
  }
  return {
    revision: Date.now(),
    source,
    outfitId,
    candidates,
    unsupportedItems,
  }
}

export function draftConflictMessages(draft: TryOnDraft): string[] {
  const messages = TRYON_REFERENCE_TYPES
    .filter((type) => (draft.candidates[type]?.length ?? 0) > 1)
    .map((type) => `${TRYON_REFERENCE_LABELS[type]}有多件商品，請選擇一件。`)
  if (
    draft.candidates.overall?.length
    && (draft.candidates.upper?.length || draft.candidates.lower?.length)
  ) {
    messages.push('連身服飾不可與上身或下身同時使用，請選擇一種穿搭模式。')
  }
  return messages
}
