import { computed, ref } from 'vue'
import {
  addStylePreference,
  addOutfitPreferenceReaction,
  confirmSoftPreferences,
  deleteStylePreference,
  getFavorites,
  getPreferenceBundle,
  patchStylePreference,
  updateFavoriteItems,
  updateFavoriteOutfit,
} from '../api'
import type {
  FavoriteItem,
  FavoriteOutfit,
  PreferenceBundle,
  StylePreference,
  StylePreferenceCreate,
  PreferenceType,
  RequirementSummary,
} from '../types'

const favoriteItems = ref<FavoriteItem[]>([])
const favoriteOutfits = ref<FavoriteOutfit[]>([])
const stylePreferences = ref<StylePreference[]>([])
const favoritesLoading = ref(false)
const preferencesLoading = ref(false)

function normalizedOrigin(itemIds: Array<number | string>): string {
  return [...new Set(itemIds.map(String))].sort().join(':')
}

function normalizedOutfit(itemIds: number[]): string {
  return [...new Set(itemIds)].sort((left, right) => left - right).join(':')
}

function replacePreference(updated: StylePreference): void {
  stylePreferences.value = [
    ...stylePreferences.value.filter((row) => row.id !== updated.id),
    updated,
  ].sort((left, right) => left.id - right.id)
}

export function useUserLibrary(userKey: string) {
  const favoriteItemIds = computed(
    () => new Set(favoriteItems.value.map((row) => row.item.id)),
  )

  async function loadFavorites(): Promise<void> {
    favoritesLoading.value = true
    try {
      const collection = await getFavorites(userKey)
      favoriteItems.value = collection.items
      favoriteOutfits.value = collection.outfits
    } finally {
      favoritesLoading.value = false
    }
  }

  async function loadPreferences(): Promise<PreferenceBundle> {
    preferencesLoading.value = true
    try {
      const bundle = await getPreferenceBundle(userKey)
      stylePreferences.value = bundle.soft
      return bundle
    } finally {
      preferencesLoading.value = false
    }
  }

  async function loadLibrary(): Promise<void> {
    await Promise.all([loadFavorites(), loadPreferences()])
  }

  async function setFavoriteItems(itemIds: number[], favorited: boolean): Promise<void> {
    await updateFavoriteItems(userKey, itemIds, favorited)
    await loadFavorites()
  }

  function isOutfitFavorited(itemIds: number[]): boolean {
    const signature = normalizedOutfit(itemIds)
    return favoriteOutfits.value.some(
      (outfit) => normalizedOutfit(outfit.items.map((item) => item.id)) === signature,
    )
  }

  async function setFavoriteOutfit(itemIds: number[], favorited: boolean): Promise<void> {
    const collection = await updateFavoriteOutfit(userKey, itemIds, favorited)
    favoriteItems.value = collection.items
    favoriteOutfits.value = collection.outfits
  }

  function outfitPreference(itemIds: Array<number | string>): StylePreference | null {
    const origin = normalizedOrigin(itemIds)
    return stylePreferences.value.find(
      (row) => row.is_active && normalizedOrigin(row.origin_item_ids) === origin,
    ) ?? null
  }

  async function confirmPreferences(rows: StylePreferenceCreate[]): Promise<void> {
    await confirmSoftPreferences(userKey, rows)
    await loadPreferences()
  }

  async function deactivatePreferenceOrigin(
    itemIds: Array<number | string>,
  ): Promise<number> {
    const origin = normalizedOrigin(itemIds)
    const matches = stylePreferences.value.filter(
      (row) => row.is_active && normalizedOrigin(row.origin_item_ids) === origin,
    )
    const updated = await Promise.all(
      matches.map((row) => patchStylePreference(userKey, row.id, { is_active: false })),
    )
    updated.forEach(replacePreference)
    return updated.length
  }

  async function addPreference(row: StylePreferenceCreate): Promise<StylePreference> {
    const updated = await addStylePreference(userKey, row)
    replacePreference(updated)
    return updated
  }

  async function addOutfitReaction(
    itemIds: number[],
    userRequest: string,
    requirements: RequirementSummary | null,
    preferenceType: PreferenceType,
  ): Promise<StylePreference> {
    const updated = await addOutfitPreferenceReaction(userKey, {
      user_key: userKey,
      user_request: userRequest,
      outfit_item_ids: itemIds,
      preference_type: preferenceType,
      requirements,
    })
    replacePreference(updated)
    return updated
  }

  async function patchPreference(
    id: number,
    patch: { is_active?: boolean; preference_text?: string },
  ): Promise<StylePreference> {
    const updated = await patchStylePreference(userKey, id, patch)
    replacePreference(updated)
    return updated
  }

  async function removePreference(id: number): Promise<void> {
    await deleteStylePreference(userKey, id)
    stylePreferences.value = stylePreferences.value.filter((row) => row.id !== id)
  }

  return {
    favoriteItems,
    favoriteItemIds,
    favoriteOutfits,
    favoritesLoading,
    stylePreferences,
    preferencesLoading,
    loadFavorites,
    loadPreferences,
    loadLibrary,
    setFavoriteItems,
    isOutfitFavorited,
    setFavoriteOutfit,
    outfitPreference,
    confirmPreferences,
    deactivatePreferenceOrigin,
    addPreference,
    addOutfitReaction,
    patchPreference,
    removePreference,
  }
}
