<script setup lang="ts">
import { ref } from 'vue'
import { Upload } from 'lucide-vue-next'
import { getSimilarClothes } from '../api'
import ProductCard from '../components/ProductCard.vue'
import type { ClothResult, GarmentZone } from '../types'

const similarItems = ref<ClothResult[]>([])
const loading = ref(false)
const error = ref('')
const activeType = ref<GarmentZone | null>(null)
const uploadedNames = ref<Partial<Record<GarmentZone, string>>>({})

const uploadOptions: Array<{ type: GarmentZone; label: string }> = [
  { type: 'upper_body', label: '上衣' },
  { type: 'lower_body', label: '下身' },
  { type: 'one_piece', label: '連身' },
  // Shoes are currently imported into the catalog's `other` garment zone.
  { type: 'other', label: '鞋子' },
]

async function searchSimilar(event: Event, option: { type: GarmentZone; label: string }) {
  const input = event.target as HTMLInputElement
  const image = input.files?.[0]
  if (!image || loading.value) return
  loading.value = true
  error.value = ''
  activeType.value = option.type
  uploadedNames.value = { ...uploadedNames.value, [option.type]: image.name }
  try {
    similarItems.value = await getSimilarClothes(image, option.type)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '無法搜尋相似商品'
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

    <p v-if="error" class="error-banner">{{ error }}</p>
    <p v-else-if="loading" class="similarity-status">正在找相似商品…</p>
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
