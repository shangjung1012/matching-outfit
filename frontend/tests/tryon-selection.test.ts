import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { CatalogItem, WardrobeCategory, WardrobeItem } from '../src/types.ts'
import {
  createTryOnDraft,
  draftConflictMessages,
  referenceTypeForCatalogItem,
  referenceTypeForWardrobeItem,
} from '../src/utils/tryOnSelection.ts'

function item(id: number, overrides: Partial<CatalogItem>): CatalogItem {
  return {
    id,
    source_item_id: id,
    product_display_name: `Item ${id}`,
    garment_zone: 'other',
    image_url: `/media/${id}.jpg`,
    price: 100,
    original_price: null,
    discounted_price: null,
    currency: 'TWD',
    brand_name: null,
    age_group: null,
    gender: null,
    master_category: null,
    sub_category: null,
    article_type: null,
    base_colour: null,
    season: null,
    year: null,
    usage: null,
    has_embedding: true,
    ...overrides,
  }
}

test('catalog items map only to supported try-on slots', () => {
  assert.equal(referenceTypeForCatalogItem(item(1, { garment_zone: 'upper_body' })), 'upper')
  assert.equal(referenceTypeForCatalogItem(item(2, { garment_zone: 'lower_body' })), 'lower')
  assert.equal(referenceTypeForCatalogItem(item(3, { garment_zone: 'one_piece' })), 'overall')
  assert.equal(referenceTypeForCatalogItem(item(4, {
    garment_zone: 'accessory', sub_category: 'Shoes', article_type: 'Sneakers',
  })), 'shoe')
  assert.equal(referenceTypeForCatalogItem(item(5, {
    garment_zone: 'accessory', sub_category: 'Bags', article_type: 'Shoulder bag',
  })), 'bag')
  assert.equal(referenceTypeForCatalogItem(item(6, {
    garment_zone: 'accessory', sub_category: 'Accessories', article_type: 'Scarf',
  })), null)
  assert.equal(referenceTypeForCatalogItem(item(7, { garment_zone: 'other' })), null)
  assert.equal(referenceTypeForCatalogItem(item(8, {
    garment_zone: 'accessory',
    master_category: 'Shoes',
    product_display_name: 'Shoe care travel pouch',
    sub_category: 'Accessories',
    article_type: 'Care kit',
  })), null)
})

test('outfit drafts retain unsupported items and expose duplicate and mode conflicts', () => {
  const draft = createTryOnDraft([
    item(1, { garment_zone: 'upper_body' }),
    item(2, { garment_zone: 'upper_body' }),
    item(3, { garment_zone: 'lower_body' }),
    item(4, { garment_zone: 'one_piece' }),
    item(5, { garment_zone: 'accessory', article_type: 'Scarf' }),
  ], 'favorite-outfit', 10)

  assert.deepEqual(draft.candidates.upper?.map((row) => row.id), [1, 2])
  assert.deepEqual(draft.candidates.lower?.map((row) => row.id), [3])
  assert.deepEqual(draft.candidates.overall?.map((row) => row.id), [4])
  assert.deepEqual(draft.unsupportedItems.map((row) => row.id), [5])
  assert.equal(draft.outfitId, 10)
  assert.deepEqual(draftConflictMessages(draft), [
    '上身有多件商品，請選擇一件。',
    '連身服飾不可與上身或下身同時使用，請選擇一種穿搭模式。',
  ])
})

test('all wardrobe categories map to the five try-on slots', () => {
  const mappings: Array<[WardrobeCategory, string]> = [
    ['upper_body', 'upper'],
    ['lower_body', 'lower'],
    ['one_piece', 'overall'],
    ['shoes', 'shoe'],
    ['bags', 'bag'],
  ]
  mappings.forEach(([category, expected], index) => {
    const wardrobeItem = { id: index + 1, category } as WardrobeItem
    assert.equal(referenceTypeForWardrobeItem(wardrobeItem), expected)
  })
})
