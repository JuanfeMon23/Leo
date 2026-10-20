<script setup lang="ts">
import type { SessionStatus } from '../types/sessions'
import { sessionStatusVariant } from '../utils/sessionStatus'

/** Insignia del estado de una sesión («Activa», «Inactiva por tiempo», «Revocada») con el motivo debajo si lo hay. */
defineProps<{ status: SessionStatus }>()
</script>

<template>
  <div data-testid="session-status" :data-status="status.kind">
    <UiStatusBadge :variant="sessionStatusVariant(status.kind)" :label="status.label" dot />
    <div v-if="status.reason" class="mt-0.5 text-xs text-text-muted" data-testid="session-reason">{{ status.reason }}</div>
  </div>
</template>
