import { ref } from 'vue'
import { useToast } from './useToast'
import type { PipelineDebugSession } from '../types'

export interface DebugHistoryItem {
  id: string
  userKey: string
  savedAt: string
  title: string
  stage: string
}

interface StoredDebug extends DebugHistoryItem {
  trace: PipelineDebugSession
}

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('matching-outfit-debug', 1)
    request.onupgradeneeded = () => {
      const store = request.result.createObjectStore('snapshots', { keyPath: 'id' })
      store.createIndex('userKey', 'userKey')
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('除錯資料庫被其他分頁占用，請關閉舊分頁後重試'))
  })
}

async function transaction<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await database()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('snapshots', mode)
    let result: T
    const request = action(tx.objectStore('snapshots'))
    request.onsuccess = () => { result = request.result }
    tx.oncomplete = () => { db.close(); resolve(result) }
    tx.onerror = tx.onabort = () => { db.close(); reject(tx.error ?? new Error('除錯紀錄儲存失敗')) }
  })
}

export function useDebugHistory(userKey: string) {
  const { showError } = useToast()
  const history = ref<DebugHistoryItem[]>([])
  const selected = ref<PipelineDebugSession | null>(null)
  const selectedId = ref<string | null>(null)
  let queue = Promise.resolve()

  function report(reason: unknown) {
    showError(`除錯歷史保存／讀取失敗：${reason instanceof Error ? reason.message : String(reason)}。可下載目前 JSON 備份。`)
  }

  async function load() {
    try {
      const rows = await transaction<StoredDebug[]>('readonly', store => store.index('userKey').getAll(userKey))
      history.value = rows.map(({ trace: _trace, ...metadata }) => metadata)
        .sort((a, b) => b.savedAt.localeCompare(a.savedAt))
    } catch (reason) { report(reason) }
  }

  function save(trace: PipelineDebugSession) {
    if (!trace.messages.some(message => message.role === 'user')) return Promise.resolve()
    const snapshot: PipelineDebugSession = JSON.parse(JSON.stringify(trace))
    const row: StoredDebug = {
      id: crypto.randomUUID(), userKey, savedAt: trace.updated_at,
      title: (trace.original_input || trace.messages.filter(message => message.role === 'user').map(message => message.text).join('；')).slice(0, 160),
      stage: trace.recommendation_debug ? '配對結果' : trace.plan_debug ? 'Query 規劃' : '需求整理',
      trace: snapshot,
    }
    queue = queue.then(async () => {
      await transaction('readwrite', store => store.put(row))
      history.value = [row, ...history.value].map(({ id, userKey, savedAt, title, stage }) => ({ id, userKey, savedAt, title, stage }))
    }).catch(report)
    return queue
  }

  async function select(id: string) {
    try {
      const row = await transaction<StoredDebug | undefined>('readonly', store => store.get(id))
      if (!row || row.userKey !== userKey) throw new Error('找不到這次紀錄')
      selected.value = row.trace
      selectedId.value = id
    } catch (reason) { report(reason) }
  }

  function showCurrent() { selected.value = null; selectedId.value = null }

  async function remove(id: string) {
    try {
      const row = await transaction<StoredDebug | undefined>('readonly', store => store.get(id))
      if (!row || row.userKey !== userKey) throw new Error('找不到這次紀錄')
      await transaction('readwrite', store => store.delete(id))
      history.value = history.value.filter(item => item.id !== id)
      if (selectedId.value === id) showCurrent()
    } catch (reason) { report(reason) }
  }

  return { history, selected, selectedId, load, save, select, showCurrent, remove }
}
