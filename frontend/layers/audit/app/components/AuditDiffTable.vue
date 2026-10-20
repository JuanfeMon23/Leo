<script setup lang="ts">
import type { AuditDiffKind } from '../utils/auditDiff'
import { auditDiffRows } from '../utils/auditDiff'

/**
 * Qué cambió en un evento: tabla «campo · antes → después». Lo modificado va
 * resaltado (color + marca de texto, no solo color); los campos sensibles no
 * muestran valores. Sin `changes`, lo dice.
 */
const props = defineProps<{ changes: Record<string, unknown> | null }>()

const rows = computed(() => auditDiffRows(props.changes))

const KIND_LABELS: Record<AuditDiffKind, string> = {
  changed: 'Modificado', added: 'Agregado', removed: 'Quitado', unchanged: 'Sin cambio'
}
const KIND_VARIANTS = { changed: 'warning', added: 'success', removed: 'danger', unchanged: 'neutral' } as const
</script>

<template>
  <p v-if="rows.length === 0" class="rounded-md bg-default-100 px-3 py-2 text-sm text-text-muted" data-testid="diff-empty">
    Este evento no registra cambios de datos.
  </p>
  <div v-else class="overflow-x-auto">
    <table class="w-full border-separate border-spacing-0 text-left text-sm" data-testid="diff-table">
      <thead>
        <tr>
          <th scope="col" class="h-9 bg-default-100 px-3 text-xs font-semibold text-text-muted first:rounded-l-md">Campo</th>
          <th scope="col" class="h-9 bg-default-100 px-3 text-xs font-semibold text-text-muted">Antes</th>
          <th scope="col" class="h-9 bg-default-100 px-3 text-xs font-semibold text-text-muted">Después</th>
          <th scope="col" class="h-9 bg-default-100 px-3 text-xs font-semibold text-text-muted last:rounded-r-md">Cambio</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.field" :data-kind="row.kind" data-testid="diff-row">
          <td class="px-3 py-2 align-top">
            <div class="font-medium text-text">{{ row.label }}</div>
            <div v-if="row.label !== row.field" class="text-xs text-text-muted"><code>{{ row.field }}</code></div>
          </td>
          <td class="break-words px-3 py-2 align-top" :class="row.kind === 'changed' || row.kind === 'removed' ? 'bg-danger-50 text-danger-700' : 'text-text-muted'" data-testid="diff-before">
            {{ row.before }}
          </td>
          <td class="break-words px-3 py-2 align-top" :class="row.kind === 'changed' || row.kind === 'added' ? 'bg-success-50 text-success-800' : 'text-text-muted'" data-testid="diff-after">
            {{ row.after }}
          </td>
          <td class="px-3 py-2 align-top">
            <UiStatusBadge :variant="KIND_VARIANTS[row.kind]" :label="KIND_LABELS[row.kind]" />
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
