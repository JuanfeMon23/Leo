<script setup lang="ts">
import type { AuditResult } from '../types/audit'
import { auditResultLabel, auditResultVariant } from '../utils/auditLabels'

/** Insignia del resultado de un evento: «Permitido» (verde), «Denegado» (ámbar), «Error» (rojo). */
defineProps<{ result: AuditResult }>()
</script>

<template>
  <span data-testid="audit-result" :data-result="result">
    <UiStatusBadge :variant="auditResultVariant(result)" :label="auditResultLabel(result)" dot />
  </span>
</template>
