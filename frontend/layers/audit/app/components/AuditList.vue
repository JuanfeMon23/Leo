<script setup lang="ts">
import type { UiDataTableColumn } from '#andromeda/components/ui/UiDataTable.vue'
import type { AuditEventRead } from '../types/audit'
import {
  auditActionName, auditActorLabel, auditApplicationName, auditEntityLabel, auditModuleName
} from '../utils/auditLabels'

/**
 * Visor de auditoría: filtros, tabla de eventos (más recientes primero),
 * detalle con el diff y exportación a CSV (`leo.audit.export`). Cada fila
 * dice qué acción, sobre qué, quién, cuándo y de qué módulo de qué aplicación.
 */
const list = useAuditList()
const exporter = useAuditExport(() => list.applied.value)

const selected = ref<AuditEventRead | null>(null)
const detailOpen = ref(false)

function openDetail(event: AuditEventRead) {
  selected.value = event
  detailOpen.value = true
}

onMounted(() => {
  void list.load()
  void list.loadLookups()
})

const columns: UiDataTableColumn<AuditEventRead>[] = [
  { key: 'occurred_at', label: 'Cuándo' },
  { key: 'actor_username', label: 'Quién' },
  { key: 'module', label: 'Aplicación → módulo' },
  { key: 'action_tag', label: 'Acción' },
  { key: 'entity_type', label: 'Sobre qué' },
  { key: 'result', label: 'Resultado' },
  { key: 'id', label: 'Detalle', class: 'text-right' }
]
</script>

<template>
  <div class="space-y-4">
    <UiPageHeader title="Auditoría" description="Registro de quién hizo qué, sobre qué, cuándo y con qué resultado en todas las aplicaciones.">
      <template #actions>
        <LeoCan tag="leo.audit.export">
          <UiButton variant="secondary" :loading="exporter.exporting.value" data-testid="audit-export" @click="exporter.run()">
            Exportar CSV
          </UiButton>
        </LeoCan>
      </template>
    </UiPageHeader>

    <AuditFilters
      v-model="list.draft.value"
      :applications="list.applications.value"
      :users="list.users.value"
      :catalog="list.catalog.value"
      :loading="list.loading.value"
      @search="list.search()"
      @clear="list.clear()"
    />

    <UiAlert v-if="list.error.value" :message="list.error.value" data-testid="audit-error" />
    <UiAlert v-if="exporter.error.value" :message="exporter.error.value" data-testid="audit-export-error" />
    <UiAlert
      v-if="list.lookupError.value"
      variant="warning"
      :message="`No se pudieron cargar algunos nombres (aplicaciones, módulos, usuarios): ${list.lookupError.value} Se muestran los identificadores técnicos.`"
      data-testid="audit-lookup-error"
    />

    <UiDataTable
      v-model:page="list.page.value"
      :columns="columns"
      :rows="list.items.value"
      :loading="list.loading.value"
      :page-size="list.pageSize"
      :total="list.total.value"
      empty-message="No hay eventos de auditoría para estos filtros."
    >
      <template #cell-occurred_at="{ row }">
        <span class="whitespace-nowrap" data-testid="audit-when">{{ formatLocalDateTime(row.occurred_at) }}</span>
      </template>
      <template #cell-actor_username="{ row }">
        <span data-testid="audit-actor">{{ auditActorLabel(row) }}</span>
      </template>
      <template #cell-module="{ row }">
        <div data-testid="audit-context">
          {{ auditApplicationName(list.catalog.value, row.application_id) }}
          <span class="text-text-muted">→</span>
          {{ auditModuleName(list.catalog.value, row.application_id, row.module) }}
        </div>
      </template>
      <template #cell-action_tag="{ row }">
        <div class="font-medium text-text" data-testid="audit-action">{{ auditActionName(list.catalog.value, row.application_id, row.action_tag) }}</div>
        <div class="text-xs text-text-muted/80"><code>{{ row.action_tag }}</code></div>
      </template>
      <template #cell-entity_type="{ row }">
        <div v-if="auditEntityLabel(row)" data-testid="audit-entity">
          {{ auditEntityLabel(row)?.type }}
          <div v-if="auditEntityLabel(row)?.id" class="max-w-40 truncate text-xs text-text-muted" :title="auditEntityLabel(row)?.id ?? undefined">
            <code>{{ auditEntityLabel(row)?.id }}</code>
          </div>
        </div>
        <span v-else class="text-text-muted">—</span>
      </template>
      <template #cell-result="{ row }">
        <AuditResultBadge :result="row.result" />
      </template>
      <template #cell-id="{ row }">
        <UiButton variant="ghost" size="sm" data-testid="audit-view" @click="openDetail(row)">Ver detalle</UiButton>
      </template>
    </UiDataTable>

    <AuditEventDetail v-model:open="detailOpen" :event="selected" :catalog="list.catalog.value" />
  </div>
</template>
