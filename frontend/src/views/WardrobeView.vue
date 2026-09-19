<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Heart, ImagePlus, Shirt, Trash2, Upload, X } from 'lucide-vue-next'
import {
  getWardrobeItems,
  removeWardrobeItem,
  setWardrobeFavorite,
  uploadWardrobeItem,
} from '../api'
import { useToast } from '../composables/useToast'
import type { WardrobeCategory, WardrobeItem } from '../types'

const props = defineProps<{ userKey: string }>()
const { showError, showSuccess } = useToast()

const items = ref<WardrobeItem[]>([])
const loading = ref(false)
const uploading = ref(false)
const uploadOpen = ref(false)
const uploadCategory = ref<WardrobeCategory>('upper_body')
const selectedFiles = ref<File[]>([])
const categoryFilter = ref<'all' | WardrobeCategory>('all')
const collectionFilter = ref<'all' | 'favorites'>('all')
const actionItemId = ref<number | null>(null)

const categories: Array<{ value: WardrobeCategory; label: string }> = [
  { value: 'upper_body', label: '上裝' },
  { value: 'lower_body', label: '下裝' },
  { value: 'one_piece', label: '連身' },
  { value: 'shoes', label: '鞋子' },
  { value: 'bags', label: '包包' },
]

const visibleItems = computed(() => items.value.filter((item) => (
  (categoryFilter.value === 'all' || item.category === categoryFilter.value)
  && (collectionFilter.value === 'all' || item.is_favorite)
)))
const favoriteCount = computed(() => items.value.filter((item) => item.is_favorite).length)

function categoryLabel(category: WardrobeCategory) {
  return categories.find((row) => row.value === category)?.label ?? category
}

async function loadItems() {
  loading.value = true
  try {
    items.value = await getWardrobeItems(props.userKey)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '無法載入我的衣櫃')
  } finally {
    loading.value = false
  }
}

function chooseFiles(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFiles.value = Array.from(input.files ?? [])
}

function closeUpload() {
  if (uploading.value) return
  uploadOpen.value = false
  selectedFiles.value = []
}

async function uploadSelected() {
  if (!selectedFiles.value.length || uploading.value) return
  uploading.value = true
  try {
    const uploaded: WardrobeItem[] = []
    for (const file of selectedFiles.value) {
      uploaded.push(await uploadWardrobeItem(props.userKey, uploadCategory.value, file))
    }
    items.value = [...uploaded.reverse(), ...items.value]
    showSuccess(`已加入 ${uploaded.length} 件單品，名稱取自圖片檔名。`)
    uploadOpen.value = false
    selectedFiles.value = []
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '衣櫃圖片上傳失敗')
    await loadItems()
  } finally {
    uploading.value = false
  }
}

async function toggleFavorite(item: WardrobeItem) {
  if (actionItemId.value !== null) return
  actionItemId.value = item.id
  try {
    const updated = await setWardrobeFavorite(props.userKey, item.id, !item.is_favorite)
    items.value = items.value.map((row) => row.id === updated.id ? updated : row)
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '無法更新衣櫃收藏')
  } finally {
    actionItemId.value = null
  }
}

async function removeItem(item: WardrobeItem) {
  if (!window.confirm(`確定要從衣櫃刪除「${item.name}」嗎？`)) return
  actionItemId.value = item.id
  try {
    await removeWardrobeItem(props.userKey, item.id)
    items.value = items.value.filter((row) => row.id !== item.id)
    showSuccess('已從我的衣櫃移除。')
  } catch (reason) {
    showError(reason instanceof Error ? reason.message : '無法刪除衣櫃單品')
  } finally {
    actionItemId.value = null
  }
}

onMounted(() => void loadItems())
</script>

<template>
  <section class="page-view wardrobe-view">
    <header class="view-heading wardrobe-heading">
      <div>
        <span class="section-kicker">My wardrobe</span>
        <h2>我的衣櫃</h2>
        <p>{{ items.length }} 件單品 · {{ favoriteCount }} 件衣櫃收藏</p>
      </div>
      <button class="primary-button" type="button" @click="uploadOpen = true">
        <Upload :size="17" />上傳單品
      </button>
    </header>

    <div class="wardrobe-toolbar">
      <div class="wardrobe-tabs" aria-label="衣櫃收藏篩選">
        <button :class="{ active: collectionFilter === 'all' }" @click="collectionFilter = 'all'">全部</button>
        <button :class="{ active: collectionFilter === 'favorites' }" @click="collectionFilter = 'favorites'">
          <Heart :size="15" />已收藏
        </button>
      </div>
      <div class="wardrobe-tabs category-tabs" aria-label="衣櫃分類">
        <button :class="{ active: categoryFilter === 'all' }" @click="categoryFilter = 'all'">所有分類</button>
        <button
          v-for="category in categories"
          :key="category.value"
          :class="{ active: categoryFilter === category.value }"
          @click="categoryFilter = category.value"
        >{{ category.label }}</button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">正在載入我的衣櫃…</div>
    <div v-else-if="visibleItems.length" class="wardrobe-grid">
      <article v-for="item in visibleItems" :key="item.id" class="wardrobe-card">
        <div class="wardrobe-card-media">
          <img :src="item.image_url" :alt="item.name" />
          <button
            type="button"
            class="wardrobe-favorite-button"
            :class="{ active: item.is_favorite }"
            :disabled="actionItemId === item.id"
            :title="item.is_favorite ? '取消衣櫃收藏' : '收藏到我的衣櫃'"
            @click="toggleFavorite(item)"
          >
            <Heart :size="19" :fill="item.is_favorite ? 'currentColor' : 'none'" />
          </button>
        </div>
        <div class="wardrobe-card-body">
          <div><strong>{{ item.name }}</strong><small>{{ categoryLabel(item.category) }}</small></div>
          <button type="button" class="icon-button" title="刪除單品" :disabled="actionItemId === item.id" @click="removeItem(item)">
            <Trash2 :size="17" />
          </button>
        </div>
      </article>
    </div>
    <div v-else class="empty-view wardrobe-empty">
      <Shirt :size="34" />
      <h3>{{ collectionFilter === 'favorites' ? '還沒有衣櫃收藏' : '衣櫃目前是空的' }}</h3>
      <p>{{ collectionFilter === 'favorites' ? '點單品右上角的愛心，就會收藏在這裡。' : '上傳自己的上裝、下裝、連身、鞋子或包包開始整理。' }}</p>
      <button v-if="collectionFilter === 'all'" class="primary-button" @click="uploadOpen = true"><ImagePlus :size="17" />上傳單品</button>
    </div>

    <div v-if="uploadOpen" class="reference-picker-backdrop" @click.self="closeUpload">
      <section class="reference-picker wardrobe-uploader" role="dialog" aria-modal="true" aria-labelledby="wardrobe-upload-title">
        <header>
          <div><span class="section-kicker">Add to wardrobe</span><h2 id="wardrobe-upload-title">上傳衣櫃單品</h2></div>
          <button class="icon-button" type="button" title="關閉" :disabled="uploading" @click="closeUpload"><X :size="18" /></button>
        </header>
        <div class="reference-type-control">
          <button v-for="category in categories" :key="category.value" :class="{ active: uploadCategory === category.value }" @click="uploadCategory = category.value">
            {{ category.label }}
          </button>
        </div>
        <label class="reference-dropzone wardrobe-dropzone">
          <ImagePlus :size="30" />
          <strong>{{ selectedFiles.length ? `已選擇 ${selectedFiles.length} 張圖片` : '選擇一張或多張照片' }}</strong>
          <small>商品名稱會使用圖片檔名，例如「藍色襯衫.jpg」會顯示為「藍色襯衫」</small>
          <input type="file" multiple accept="image/jpeg,image/png,image/webp" :disabled="uploading" @change="chooseFiles" />
        </label>
        <ul v-if="selectedFiles.length" class="wardrobe-file-list">
          <li v-for="file in selectedFiles" :key="`${file.name}-${file.size}`">{{ file.name }}</li>
        </ul>
        <footer>
          <button class="secondary-button" type="button" :disabled="uploading" @click="closeUpload">取消</button>
          <button class="primary-button" type="button" :disabled="!selectedFiles.length || uploading" @click="uploadSelected">
            {{ uploading ? '正在上傳…' : `加入 ${categoryLabel(uploadCategory)}` }}
          </button>
        </footer>
      </section>
    </div>
  </section>
</template>
