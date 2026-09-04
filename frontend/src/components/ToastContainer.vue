<script setup lang="ts">
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-vue-next'
import { useToast, type ToastAction } from '../composables/useToast'

const { toasts, dismissToast } = useToast()

const icons = { error: AlertCircle, success: CheckCircle2, info: Info }

function runAction(id: number, action?: ToastAction) {
  if (!action) return
  action.onClick()
  dismissToast(id)
}
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="toast"
        :class="`toast-${toast.type}`"
        role="status"
      >
        <component :is="icons[toast.type]" :size="16" class="toast-icon" />
        <p>{{ toast.message }}</p>
        <button
          v-if="toast.action"
          type="button"
          class="toast-action"
          @click="runAction(toast.id, toast.action)"
        >
          {{ toast.action.label }}
        </button>
        <button
          type="button"
          class="toast-close"
          aria-label="關閉通知"
          @click="dismissToast(toast.id)"
        >
          <X :size="13" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
