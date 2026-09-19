<script setup lang="ts">
import { ref } from 'vue'
import { Upload } from 'lucide-vue-next'
import { getSimilarClothes } from '../api'
import ProductCard from '../components/ProductCard.vue'
import { useToast } from '../composables/useToast'
import type { GarmentZone, SimilarCatalogItem, TryOnReferenceType } from '../types'

const { showError } = useToast()
const similarItems = ref<SimilarCatalogItem[]>([])
const loading = ref(false)
const activeType = ref<GarmentZone | null>(null)
const uploadedNames = ref<Partial<Record<GarmentZone, string>>>({})

const uploadOptions: Array<{ type: GarmentZone; referenceType: TryOnReferenceType; label: string }> = [
  { type: 'upper_body', referenceType: 'upper', label: '上衣' },
  { type: 'lower_body', referenceType: 'lower', label: '下身' },
  { type: 'one_piece', referenceType: 'overall', label: '連身' },
  { type: 'accessory', referenceType: 'shoe', label: '鞋子' },
]

async function searchSimilar(
  event: Event,
  option: { type: GarmentZone; referenceType: TryOnReferenceType; label: string },
) {
  const input = event.target as HTMLInputElement
  const image = input.files?.[0]
  if (!image || loading.value) return
  loading.value = true
  activeType.value = option.type
  uploadedNames.value = { ...uploadedNames.value, [option.type]: image.name }
  try {
    similarItems.value = await getSimilarClothes(image, option.type, 24, option.referenceType)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '無法搜尋相似商品')
    similarItems.value = []
  } finally {
    loading.value = false
    input.value = ''
  }
}
</script>

<template>
  <section class="page-view similarity-view">
    <header class="similarity-heading">
      <span class="section-kicker">Visual search</span>
      <h2>找相似</h2>
    </header>

    <div class="similarity-upload-stack">
      <label v-for="option in uploadOptions" :key="option.type" class="similarity-upload-block">
        <input class="similarity-file-input" type="file" accept="image/jpeg,image/png,image/webp" @change="searchSimilar($event, option)" />
        <Upload :size="21" />
        <strong>上傳{{ option.label }}</strong>
        <small v-if="uploadedNames[option.type]">{{ uploadedNames[option.type] }}</small>
      </label>
    </div>

    <p v-if="loading" class="similarity-status">正在找相似商品…</p>
    <template v-else-if="activeType">
      <header class="similarity-results-heading">
        <div>
          <span class="section-kicker">Similar items</span>
          <h3>相似{{ uploadOptions.find((option) => option.type === activeType)?.label }}</h3>
        </div>
        <span>{{ similarItems.length }} 件結果</span>
      </header>
      <div v-if="similarItems.length" class="product-grid similarity-product-grid">
        <ProductCard v-for="item in similarItems" :key="item.id" :item="item" show-similarity />
      </div>
      <p v-else class="similarity-status">沒有找到相似商品。</p>
    </template>
  </section>
</template>
