<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Search, Shirt } from 'lucide-vue-next'
import { getCatalog } from '../api'
import ProductCard from '../components/ProductCard.vue'
import type { CatalogItem } from '../types'

const items = ref<CatalogItem[]>([])
const total = ref(0)
const zone = ref('')
const search = ref('')
const loading = ref(false)
const error = ref('')

const zones = [
  { value: '', label: '全部' },
  { value: 'upper_body', label: '上半身' },
  { value: 'lower_body', label: '下半身' },
  { value: 'one_piece', label: '單件套裝' },
  { value: 'accessory', label: '配件' },
]

async function loadCatalog() {
  loading.value = true
  error.value = ''
  try {
    const response = await getCatalog(zone.value, search.value.trim())
    items.value = response.items
    total.value = response.total
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '無法載入商品'
  } finally {
    loading.value = false
  }
}

onMounted(loadCatalog)
</script>

<template>
  <section class="page-view catalog-view">
    <header class="view-heading">
      <div>
        <span class="section-kicker">Catalog</span>
        <h2>衣服商品</h2>
        <p>{{ total }} 件已匯入商品</p>
      </div>
      <div class="catalog-search">
        <Search :size="17" />
        <input v-model="search" placeholder="搜尋名稱、顏色或品類" @keyup.enter="loadCatalog" />
      </div>
    </header>

    <div class="filter-toolbar">
      <div class="segmented-control" aria-label="商品分類">
        <button
          v-for="option in zones"
          :key="option.value"
          :class="{ active: zone === option.value }"
          @click="zone = option.value; loadCatalog()"
        >
          {{ option.label }}
        </button>
      </div>
      <button class="secondary-button" @click="loadCatalog"><Search :size="16" />搜尋</button>
    </div>

    <p v-if="error" class="error-banner">{{ error }}</p>
    <div v-if="loading" class="loading-state">正在載入商品…</div>
    <div v-else-if="items.length" class="product-grid">
      <ProductCard v-for="item in items" :key="item.id" :item="item" />
    </div>
    <div v-else class="empty-view">
      <Shirt :size="32" />
      <h3>沒有符合條件的商品</h3>
    </div>
  </section>
</template>
