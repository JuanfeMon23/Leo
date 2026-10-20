<script setup lang="ts">
import type { ApplicationsGrantPermission } from '../types/applications'

/**
 * Permisos de un rol para leerse: el nombre legible es lo principal y el tag
 * técnico va pequeño y atenuado como referencia. `null` = no se pudieron cargar.
 */
defineProps<{ permissions: readonly ApplicationsGrantPermission[] | null }>()
</script>

<template>
  <p v-if="permissions === null" class="text-xs text-text-muted" data-testid="perm-unavailable">No se pudieron cargar los permisos de este rol.</p>
  <p v-else-if="permissions.length === 0" class="text-xs text-text-muted" data-testid="perm-empty">Este rol aún no tiene permisos.</p>
  <ul v-else class="space-y-0.5">
    <li v-for="permission in permissions" :key="permission.id" class="flex flex-wrap items-baseline gap-x-2" data-testid="perm-item">
      <span class="text-sm text-text" data-testid="perm-name">{{ permission.name }}</span>
      <code class="break-all text-xs text-text-muted" :title="`Tag técnico: ${permission.tag}`" data-testid="perm-tag">{{ permission.tag }}</code>
    </li>
  </ul>
</template>
