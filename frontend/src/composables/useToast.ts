import { ref } from 'vue'

export type ToastType = 'error' | 'success' | 'info'

export interface ToastAction {
  label: string
  onClick: () => void
}

export interface ToastEntry {
  id: number
  type: ToastType
  message: string
  action?: ToastAction
}

interface PushOptions {
  action?: ToastAction
  duration?: number
}

const DEFAULT_DURATIONS: Record<ToastType, number> = {
  error: 2000,
  success: 2000,
  info: 2000,
}

const toasts = ref<ToastEntry[]>([])
const timers = new Map<number, ReturnType<typeof setTimeout>>()
let nextId = 1

function clearTimer(id: number): void {
  const timer = timers.get(id)
  if (timer === undefined) return
  clearTimeout(timer)
  timers.delete(id)
}

function dismissToast(id: number): void {
  clearTimer(id)
  toasts.value = toasts.value.filter((toast) => toast.id !== id)
}

function scheduleDismiss(id: number, duration: number): void {
  clearTimer(id)
  timers.set(id, setTimeout(() => dismissToast(id), duration))
}

// Re-showing the same message (e.g. a polling error that keeps firing) refreshes
// the existing toast's timer instead of stacking duplicates on top of each other.
function pushToast(message: string, type: ToastType, options: PushOptions = {}): number {
  const duration = options.duration ?? DEFAULT_DURATIONS[type]
  const existing = toasts.value.find((toast) => toast.type === type && toast.message === message)
  if (existing) {
    existing.action = options.action
    scheduleDismiss(existing.id, duration)
    return existing.id
  }
  const id = nextId++
  toasts.value = [...toasts.value, { id, type, message, action: options.action }]
  scheduleDismiss(id, duration)
  return id
}

export function useToast() {
  return {
    toasts,
    dismissToast,
    showError: (message: string, options?: PushOptions) => pushToast(message, 'error', options),
    showSuccess: (message: string, options?: PushOptions) => pushToast(message, 'success', options),
    showInfo: (message: string, options?: PushOptions) => pushToast(message, 'info', options),
  }
}
