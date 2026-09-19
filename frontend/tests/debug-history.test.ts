import assert from 'node:assert/strict'
import { test } from 'node:test'
import { useDebugHistory } from '../src/composables/useDebugHistory.ts'

// In-memory IndexedDB adapter for unit tests; not a browser persistence test.
const records = new Map()
let quotaFailure = false
Object.defineProperty(global, 'indexedDB', { value: {
  open() {
    const request = {} as any
    setImmediate(() => {
      request.result = {
        close() {},
        transaction() {
          const tx = {} as any
          function operation(callback) {
            const req = {} as any
            setImmediate(() => {
              if (quotaFailure) { tx.error = new Error('QuotaExceededError'); tx.onabort(); return }
              req.result = callback()
              req.onsuccess()
              tx.oncomplete()
            })
            return req
          }
          tx.objectStore = () => ({
            put: row => operation(() => { records.set(row.id, structuredClone(row)); return row.id }),
            get: id => operation(() => records.has(id) ? structuredClone(records.get(id)) : undefined),
            delete: id => operation(() => records.delete(id)),
            index: () => ({ getAll: key => operation(() => [...records.values()].filter(row => row.userKey === key)) }),
          })
          return tx
        },
      }
      request.onsuccess()
    })
    return request
  },
}, configurable: true })

function trace() {
  return {
    updated_at: new Date().toISOString(), messages: [{ role: 'user', text: '女團舞' }],
    original_input: '女團舞', requirements: null, fashion_intent: null, queries: [],
    styling_guide: null, plan_debug: null, recommendation_debug: {},
    recommendations: [{}], discarded_recommendations: [], review_note: '', knowledge_note: '',
  } as any
}

test('snapshots survive a new history instance and are immutable and user scoped', async () => {
  const first = useDebugHistory('one')
  const input = trace()
  const saved = first.save(input)
  input.messages[0].text = 'later edit'
  await saved
  const id = first.history.value[0].id
  const restored = useDebugHistory('one')
  await restored.load()
  assert.equal(restored.history.value.length, 1)
  await restored.select(id)
  assert.equal(restored.selected.value?.messages[0].text, '女團舞')
  await restored.save(trace())
  assert.equal(restored.selectedId.value, id)
  const other = useDebugHistory('two')
  await other.load()
  assert.equal(other.history.value.length, 0)
  await other.select(id)
  assert.equal(other.selected.value, null)
  assert.ok(other.error.value)
  await restored.remove(id)
  assert.equal(restored.history.value.length, 1)
  assert.equal(restored.selected.value, null)
})

test('storage failure is visible without dropping existing history', async () => {
  const history = useDebugHistory('quota')
  await history.save(trace())
  quotaFailure = true
  try {
    await history.save(trace())
    assert.equal(history.history.value.length, 1)
    assert.match(history.error.value, /QuotaExceededError/)
  } finally { quotaFailure = false }
})
