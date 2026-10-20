<script setup lang="ts">
import type { RolesPermissionGroup, RolesPermissionModel } from '../types/roles'
import { rolesGroupState, rolesSelectableIds, rolesSetGroup } from '../utils/rolePermissions'

/**
 * Editor de permisos de un rol: los permisos de la aplicación agrupados por
 * módulo, con checkboxes. Lo principal de cada permiso es su nombre legible
 * (con su descripción corta); el tag técnico va pequeño y atenuado como
 * referencia. «Seleccionar todo» marca/desmarca los asignables del módulo.
 * Las acciones de evento (auditoría) no se asignan: van aparte, informativas.
 * Es controlado (`selected`); guardar lo hace quien lo usa.
 */
const props = defineProps<{
  model: RolesPermissionModel
  selected: ReadonlySet<string>
  readonly?: boolean
}>()
const emit = defineEmits<{ 'update:selected': [value: Set<string>] }>()

function toggle(id: string, on: boolean) {
  const next = new Set(props.selected)
  if (on) next.add(id)
  else next.delete(id)
  emit('update:selected', next)
}

function toggleGroup(group: RolesPermissionGroup, on: boolean) {
  emit('update:selected', rolesSetGroup(group, props.selected, on))
}

const markedIn = (group: RolesPermissionGroup) => group.permissions.filter(p => props.selected.has(p.id)).length
</script>

<template>
  <div class="space-y-4">
    <UiCard v-if="model.groups.length === 0">
      <p class="text-sm text-text-muted" data-testid="permissions-empty">Esta aplicación aún no tiene permisos que asignar.</p>
    </UiCard>

    <UiCard
      v-for="group in model.groups"
      :key="group.moduleId"
      :title="group.name"
      :description="group.description ?? undefined"
      data-testid="permission-group"
    >
      <template #actions>
        <span class="text-xs text-text-muted" data-testid="group-count">{{ markedIn(group) }} de {{ group.permissions.length }}</span>
        <UiCheckbox
          v-if="!readonly && rolesSelectableIds(group).length"
          :model-value="rolesGroupState(group, selected) === 'all'"
          :aria-label="`Seleccionar todo en ${group.name}`"
          data-testid="group-all"
          @update:model-value="toggleGroup(group, $event)"
        >
          Seleccionar todo
        </UiCheckbox>
      </template>

      <ul class="divide-y divide-border">
        <li
          v-for="permission in group.permissions"
          :key="permission.id"
          class="flex items-start justify-between gap-x-4 py-2.5"
          data-testid="permission-row"
        >
          <UiCheckbox
            class="min-w-0 flex-1"
            :model-value="selected.has(permission.id)"
            :description="permission.description ?? undefined"
            :disabled="readonly || (!permission.selectable && !selected.has(permission.id))"
            data-testid="permission-check"
            @update:model-value="toggle(permission.id, $event)"
          >
            <span class="font-medium">{{ permission.name }}</span>
            <UiStatusBadge v-if="permission.blockedReason" variant="neutral" :label="permission.blockedReason" class="ml-2 align-middle" />
          </UiCheckbox>
          <code class="shrink-0 pt-0.5 text-xs text-text-muted" :title="`Tag técnico: ${permission.tag}`" data-testid="permission-tag">{{ permission.tag }}</code>
        </li>
      </ul>
    </UiCard>

    <details v-if="model.events.length" class="rounded-lg border border-border bg-surface px-4 py-3" data-testid="events-section">
      <summary class="cursor-pointer text-sm font-semibold text-text">Eventos de auditoría ({{ model.events.length }})</summary>
      <p class="mt-2 text-sm text-text-muted">Son eventos que el sistema registra en la auditoría; no se asignan a los roles.</p>
      <ul class="mt-2 divide-y divide-border">
        <li v-for="event in model.events" :key="event.id" class="flex flex-wrap items-baseline justify-between gap-2 py-1.5 text-sm">
          <span class="text-text">{{ event.name }}</span>
          <code class="break-all text-xs text-text-muted">{{ event.tag }}</code>
        </li>
      </ul>
    </details>
  </div>
</template>
