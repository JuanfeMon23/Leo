<script setup lang="ts">
import type { AuditApplication, AuditCatalog, AuditFiltersState, AuditUser } from '../types/audit'
import { AUDIT_RESULT_OPTIONS } from '../utils/auditLabels'
import { auditActiveFilterCount } from '../utils/auditQuery'

/**
 * Formulario de filtros del visor: quién, aplicación → módulo → acción (los
 * dos últimos dependen de la aplicación elegida), entidad, resultado y rango
 * de fechas. Edita un borrador; «Buscar» lo aplica y «Limpiar» lo vacía.
 */
const filters = defineModel<AuditFiltersState>({ required: true })

const props = defineProps<{
  applications: AuditApplication[]
  users: AuditUser[]
  catalog: AuditCatalog
  loading?: boolean
}>()

const emit = defineEmits<{ search: [], clear: [] }>()

const appOptions = computed(() => props.applications.map(a => ({ value: a.id, label: a.name })))
const userOptions = computed(() =>
  props.users.map(u => ({ value: u.id, label: `${`${u.first_name} ${u.last_name}`.trim()} (${u.username})` })))

const selectedApp = computed(() => props.catalog[filters.value.applicationId])
const moduleOptions = computed(() => (selectedApp.value?.modules ?? []).map(m => ({ value: m.slug, label: m.name })))
const actionOptions = computed(() => {
  const modules = (selectedApp.value?.modules ?? []).filter(m => !filters.value.module || m.slug === filters.value.module)
  return modules.flatMap(m => m.actions.map(a => ({ value: a.tag, label: a.name })))
})

const activeCount = computed(() => auditActiveFilterCount(filters.value))

function set<K extends keyof AuditFiltersState>(key: K, value: AuditFiltersState[K]) {
  filters.value = { ...filters.value, [key]: value }
}
</script>

<template>
  <form class="space-y-4 rounded-lg bg-surface p-4 shadow-sm" data-testid="audit-filters" @submit.prevent="emit('search')">
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <UiFormField label="Quién">
        <UiSelect
          v-if="users.length"
          :model-value="filters.actorUserId"
          empty-label="Cualquier usuario"
          :options="userOptions"
          data-testid="filter-actor"
          @update:model-value="set('actorUserId', $event)"
        />
        <UiTextInput
          v-else
          :model-value="filters.actorUsername"
          placeholder="Nombre de usuario exacto"
          data-testid="filter-actor-username"
          @update:model-value="set('actorUsername', $event)"
        />
      </UiFormField>

      <UiFormField label="Aplicación">
        <UiSelect
          :model-value="filters.applicationId"
          empty-label="Todas las aplicaciones"
          :options="appOptions"
          data-testid="filter-app"
          @update:model-value="set('applicationId', $event)"
        />
      </UiFormField>

      <UiFormField label="Módulo" :hint="filters.applicationId ? undefined : 'Elige primero una aplicación.'">
        <UiSelect
          :model-value="filters.module"
          empty-label="Todos los módulos"
          :options="moduleOptions"
          :disabled="!filters.applicationId"
          data-testid="filter-module"
          @update:model-value="set('module', $event)"
        />
      </UiFormField>

      <UiFormField label="Acción">
        <UiSelect
          :model-value="filters.actionTag"
          empty-label="Todas las acciones"
          :options="actionOptions"
          :disabled="!filters.applicationId"
          data-testid="filter-action"
          @update:model-value="set('actionTag', $event)"
        />
      </UiFormField>

      <UiFormField label="Sobre qué (tipo)">
        <UiTextInput
          :model-value="filters.entityType"
          placeholder="Ej.: user, role, session"
          data-testid="filter-entity-type"
          @update:model-value="set('entityType', $event)"
        />
      </UiFormField>

      <UiFormField label="Sobre qué (identificador)">
        <UiTextInput
          :model-value="filters.entityId"
          placeholder="Identificador de la entidad"
          data-testid="filter-entity-id"
          @update:model-value="set('entityId', $event)"
        />
      </UiFormField>

      <UiFormField label="Resultado">
        <UiSelect
          :model-value="filters.result"
          empty-label="Todos los resultados"
          :options="AUDIT_RESULT_OPTIONS"
          data-testid="filter-result"
          @update:model-value="set('result', $event as AuditFiltersState['result'])"
        />
      </UiFormField>

      <div class="grid grid-cols-2 gap-2">
        <UiFormField label="Desde">
          <UiTextInput
            type="date"
            :model-value="filters.dateFrom"
            :max="filters.dateTo || undefined"
            data-testid="filter-date-from"
            @update:model-value="set('dateFrom', $event)"
          />
        </UiFormField>
        <UiFormField label="Hasta">
          <UiTextInput
            type="date"
            :model-value="filters.dateTo"
            :min="filters.dateFrom || undefined"
            data-testid="filter-date-to"
            @update:model-value="set('dateTo', $event)"
          />
        </UiFormField>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <UiButton type="submit" :loading="loading" data-testid="filter-search">Buscar</UiButton>
      <UiButton variant="ghost" :disabled="activeCount === 0" data-testid="filter-clear" @click="emit('clear')">
        Limpiar filtros
      </UiButton>
      <span v-if="activeCount" class="text-xs text-text-muted">{{ activeCount }} {{ activeCount === 1 ? 'filtro' : 'filtros' }} en edición</span>
    </div>
  </form>
</template>
