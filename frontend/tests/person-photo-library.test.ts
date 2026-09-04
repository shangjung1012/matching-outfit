import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  PERSON_PHOTO_LIMIT,
  usePersonPhotoLibrary,
  validatePersonPhoto,
} from '../src/composables/usePersonPhotoLibrary.ts'

const records = new Map<string, any>()
let storeCreated = false
let nextPutError: Error | null = null

function operation(transaction: any, callback: () => unknown) {
  transaction.pending += 1
  const request: any = {}
  setImmediate(() => {
    try {
      request.result = callback()
      request.onsuccess?.()
      transaction.pending -= 1
      setImmediate(() => {
        if (transaction.pending === 0) transaction.oncomplete?.()
      })
    } catch (reason) {
      request.error = reason
      transaction.error = reason
      request.onerror?.()
      transaction.onabort?.()
    }
  })
  return request
}

const database = {
  objectStoreNames: { contains: () => storeCreated },
  createObjectStore() {
    storeCreated = true
    return { createIndex() {} }
  },
  close() {},
  transaction() {
    const transaction: any = { pending: 0 }
    transaction.objectStore = () => ({
      put: (row: any) => operation(transaction, () => {
        if (nextPutError) {
          const reason = nextPutError
          nextPutError = null
          throw reason
        }
        records.set(row.id, structuredClone(row))
        return row.id
      }),
      delete: (id: string) => operation(transaction, () => records.delete(id)),
      index: () => ({
        getAll: (userKey: string) => operation(transaction, () => (
          [...records.values()]
            .filter((row) => row.userKey === userKey)
            .map((row) => structuredClone(row))
        )),
      }),
    })
    return transaction
  },
}

Object.defineProperty(globalThis, 'indexedDB', {
  configurable: true,
  value: {
    open() {
      const request: any = {}
      setImmediate(() => {
        request.result = database
        if (!storeCreated) request.onupgradeneeded?.()
        request.onsuccess?.()
      })
      return request
    },
  },
})

Object.defineProperty(globalThis, 'createImageBitmap', {
  configurable: true,
  value: async () => ({ width: 800, height: 1200, close() {} }),
})

function photo(name: string) {
  return new File([new Uint8Array([1, 2, 3])], `${name}.png`, { type: 'image/png' })
}

test('person photos persist by user and maintain one default through limit and deletion', async () => {
  records.clear()
  const alice = usePersonPhotoLibrary('alice')
  await alice.load()
  assert.equal(alice.photos.value.length, 0)

  for (let index = 1; index <= PERSON_PHOTO_LIMIT; index += 1) {
    await alice.add(photo(`photo-${index}`), `人物 ${index}`, 10_000, 2_000_000)
  }
  assert.equal(alice.photos.value.length, PERSON_PHOTO_LIMIT)
  assert.equal(alice.photos.value.filter((row) => row.isDefault).length, 1)
  await assert.rejects(
    alice.add(photo('overflow'), '超過上限', 10_000, 2_000_000),
    /最多只能保存 5 張/,
  )

  const nextDefault = alice.photos.value.find((row) => !row.isDefault)!
  await alice.setDefault(nextDefault.id)
  assert.equal(alice.defaultPhoto.value?.id, nextDefault.id)
  await alice.rename(nextDefault.id, '新的預設照')
  assert.equal(alice.defaultPhoto.value?.name, '新的預設照')
  await alice.remove(nextDefault.id)
  assert.equal(alice.photos.value.length, PERSON_PHOTO_LIMIT - 1)
  assert.equal(alice.photos.value.filter((row) => row.isDefault).length, 1)

  const bob = usePersonPhotoLibrary('bob')
  await bob.load()
  assert.equal(bob.photos.value.length, 0)

  const restored = usePersonPhotoLibrary('alice')
  await restored.load()
  assert.equal(restored.photos.value.length, PERSON_PHOTO_LIMIT - 1)
  assert.equal(restored.photos.value[0].blob.size, 3)
  assert.equal(restored.photos.value.filter((row) => row.isDefault).length, 1)
})

test('deleting the default promotes the most recently updated remaining photo', async () => {
  records.clear()
  const library = usePersonPhotoLibrary('replacement-user')
  await library.load()
  const first = await library.add(photo('first'), '第一張', 10_000, 2_000_000)
  const second = await library.add(photo('second'), '第二張', 10_000, 2_000_000)
  await library.rename(second.id, '最近更新')
  await library.remove(first.id)
  assert.equal(library.defaultPhoto.value?.id, second.id)
})

test('person photo validation rejects unsupported, oversized, and over-pixel images', async () => {
  await assert.rejects(
    validatePersonPhoto(new File(['text'], 'person.gif', { type: 'image/gif' }), 10_000, 2_000_000),
    /只支援 JPEG、PNG 或 WebP/,
  )
  await assert.rejects(
    validatePersonPhoto(new File([new Uint8Array(11)], 'large.png', { type: 'image/png' }), 10, 2_000_000),
    /不可超過/,
  )
  await assert.rejects(
    validatePersonPhoto(photo('pixels'), 10_000, 900_000),
    /像素不可超過/,
  )
})

test('quota failures are exposed without adding a partial photo', async () => {
  records.clear()
  const library = usePersonPhotoLibrary('quota-user')
  await library.load()
  nextPutError = new DOMException('Storage quota exceeded', 'QuotaExceededError')
  await assert.rejects(
    library.add(photo('quota'), '無法保存', 10_000, 2_000_000),
    /Storage quota exceeded/,
  )
  assert.equal(library.photos.value.length, 0)
  assert.match(library.error.value, /仍可使用一次性上傳完成試穿/)
})
