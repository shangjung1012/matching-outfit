import { computed, ref, shallowRef } from 'vue'
import type { SavedPersonPhoto } from '../types'

const DATABASE_NAME = 'matching-outfit-media'
const DATABASE_VERSION = 1
const STORE_NAME = 'personPhotos'
const MAX_PERSON_PHOTOS = 5
const ACCEPTED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])

export const PERSON_PHOTO_LIMIT = MAX_PERSON_PHOTOS

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('這個瀏覽器不支援本機人物照圖庫'))
      return
    }
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        const store = database.createObjectStore(STORE_NAME, { keyPath: 'id' })
        store.createIndex('userKey', 'userKey')
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('無法開啟人物照圖庫'))
    request.onblocked = () => reject(new Error('人物照圖庫被其他分頁占用，請關閉舊分頁後重試'))
  })
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('人物照圖庫操作失敗'))
  })
}

async function readUserPhotos(userKey: string): Promise<SavedPersonPhoto[]> {
  const database = await openDatabase()
  try {
    const transaction = database.transaction(STORE_NAME, 'readonly')
    const store = transaction.objectStore(STORE_NAME)
    return await requestResult<SavedPersonPhoto[]>(store.index('userKey').getAll(userKey))
  } finally {
    database.close()
  }
}

async function writeChanges(
  rows: SavedPersonPhoto[],
  deletedId: string | null = null,
): Promise<void> {
  const database = await openDatabase()
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    const store = transaction.objectStore(STORE_NAME)
    rows.forEach((row) => store.put(row))
    if (deletedId) store.delete(deletedId)
    transaction.oncomplete = () => { database.close(); resolve() }
    transaction.onerror = transaction.onabort = () => {
      database.close()
      reject(transaction.error ?? new Error('人物照圖庫儲存失敗'))
    }
  })
}

function byMostRecentlyUpdated(left: SavedPersonPhoto, right: SavedPersonPhoto) {
  if (left.isDefault !== right.isDefault) return left.isDefault ? -1 : 1
  return right.updatedAt.localeCompare(left.updatedAt)
}

export function normalizePersonPhotoDefaults(rows: SavedPersonPhoto[]): SavedPersonPhoto[] {
  if (!rows.length) return []
  const sorted = [...rows].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
  const defaultId = sorted.find((row) => row.isDefault)?.id ?? sorted[0].id
  return rows.map((row) => ({ ...row, isDefault: row.id === defaultId }))
}

async function imageDimensions(file: File): Promise<{ width: number; height: number }> {
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(file)
    try {
      return { width: bitmap.width, height: bitmap.height }
    } finally {
      bitmap.close()
    }
  }
  return new Promise((resolve, reject) => {
    const preview = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      URL.revokeObjectURL(preview)
      resolve({ width: image.naturalWidth, height: image.naturalHeight })
    }
    image.onerror = () => {
      URL.revokeObjectURL(preview)
      reject(new Error('無法讀取圖片尺寸'))
    }
    image.src = preview
  })
}

export async function validatePersonPhoto(
  file: File,
  maxBytes: number,
  maxPixels: number,
): Promise<{ width: number; height: number }> {
  if (!ACCEPTED_TYPES.has(file.type)) throw new Error('人物照只支援 JPEG、PNG 或 WebP')
  if (!file.size) throw new Error('請選擇有效的人物照片')
  if (file.size > maxBytes) throw new Error(`人物照不可超過 ${Math.round(maxBytes / 1048576)} MiB`)
  const dimensions = await imageDimensions(file)
  if (!dimensions.width || !dimensions.height) throw new Error('無法讀取人物照片')
  if (dimensions.width * dimensions.height > maxPixels) {
    throw new Error(`人物照像素不可超過 ${maxPixels.toLocaleString('zh-TW')}`)
  }
  return dimensions
}

function reportStorageError(reason: unknown): string {
  const message = reason instanceof Error ? reason.message : String(reason)
  return `人物照無法保存在這個瀏覽器：${message}。仍可使用一次性上傳完成試穿。`
}

export function usePersonPhotoLibrary(userKey: string) {
  // Keep Blob/File values out of Vue's deep reactive proxies so IndexedDB can clone them.
  const photos = shallowRef<SavedPersonPhoto[]>([])
  const loading = ref(false)
  const error = ref('')
  const canAdd = computed(() => photos.value.length < MAX_PERSON_PHOTOS)
  const defaultPhoto = computed(() => photos.value.find((photo) => photo.isDefault) ?? null)

  function applyRows(rows: SavedPersonPhoto[]) {
    photos.value = [...rows].sort(byMostRecentlyUpdated)
  }

  async function load() {
    loading.value = true
    try {
      const stored = await readUserPhotos(userKey)
      const normalized = normalizePersonPhotoDefaults(stored)
      const changed = normalized.some((row, index) => row.isDefault !== stored[index]?.isDefault)
      if (changed) await writeChanges(normalized)
      applyRows(normalized)
      error.value = ''
    } catch (reason) {
      error.value = reportStorageError(reason)
    } finally {
      loading.value = false
    }
  }

  async function add(
    file: File,
    name: string,
    maxBytes: number,
    maxPixels: number,
  ): Promise<SavedPersonPhoto> {
    try {
      if (photos.value.length >= MAX_PERSON_PHOTOS) {
        throw new Error(`最多只能保存 ${MAX_PERSON_PHOTOS} 張人物照，請先刪除一張`)
      }
      const dimensions = await validatePersonPhoto(file, maxBytes, maxPixels)
      const now = new Date().toISOString()
      const row: SavedPersonPhoto = {
        id: crypto.randomUUID(),
        userKey,
        name: name.trim().slice(0, 40) || `人物照 ${photos.value.length + 1}`,
        blob: file,
        mimeType: file.type,
        size: file.size,
        width: dimensions.width,
        height: dimensions.height,
        isDefault: photos.value.length === 0,
        createdAt: now,
        updatedAt: now,
      }
      const next = row.isDefault
        ? [row, ...photos.value.map((photo) => ({ ...photo, isDefault: false }))]
        : [row, ...photos.value]
      await writeChanges(next)
      applyRows(next)
      error.value = ''
      return row
    } catch (reason) {
      error.value = reportStorageError(reason)
      throw reason
    }
  }

  async function rename(id: string, name: string) {
    const trimmed = name.trim().slice(0, 40)
    if (!trimmed) throw new Error('人物照名稱不可空白')
    const photo = photos.value.find((candidate) => candidate.id === id)
    if (!photo) throw new Error('找不到這張人物照')
    const updated = { ...photo, name: trimmed, updatedAt: new Date().toISOString() }
    await writeChanges([updated])
    applyRows(photos.value.map((candidate) => candidate.id === id ? updated : candidate))
    error.value = ''
  }

  async function setDefault(id: string) {
    if (!photos.value.some((photo) => photo.id === id)) throw new Error('找不到這張人物照')
    const now = new Date().toISOString()
    const next = photos.value.map((photo) => ({
      ...photo,
      isDefault: photo.id === id,
      updatedAt: photo.id === id ? now : photo.updatedAt,
    }))
    await writeChanges(next)
    applyRows(next)
    error.value = ''
  }

  async function remove(id: string) {
    const removed = photos.value.find((photo) => photo.id === id)
    if (!removed) return
    let next = photos.value.filter((photo) => photo.id !== id)
    if (removed.isDefault && next.length) {
      const replacement = [...next].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))[0]
      next = next.map((photo) => ({ ...photo, isDefault: photo.id === replacement.id }))
    }
    await writeChanges(next, id)
    applyRows(next)
    error.value = ''
  }

  return {
    photos,
    loading,
    error,
    canAdd,
    defaultPhoto,
    load,
    add,
    rename,
    setDefault,
    remove,
  }
}
