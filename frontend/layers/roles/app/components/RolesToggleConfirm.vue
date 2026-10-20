<script setup lang="ts">
import type { RolesToggle } from '../composables/useRolesToggle'

/** Confirmación de activar/desactivar un rol (la comparten el listado y el detalle). */
const props = defineProps<{ toggle: RolesToggle }>()

const deactivating = computed(() => props.toggle.target?.is_active ?? true)
</script>

<template>
  <UiConfirmModal
    v-model:open="toggle.open"
    :title="deactivating ? 'Desactivar rol' : 'Activar rol'"
    :message="deactivating
      ? `Se desactivará «${toggle.target?.name}»: sus usuarios dejarán de recibir sus permisos. Podrás reactivarlo cuando quieras.`
      : `Se activará «${toggle.target?.name}».`"
    :confirm-label="deactivating ? 'Desactivar' : 'Activar'"
    :variant="deactivating ? 'danger' : 'primary'"
    :loading="toggle.loading"
    :error="toggle.error"
    @confirm="toggle.confirm()"
  />
</template>
