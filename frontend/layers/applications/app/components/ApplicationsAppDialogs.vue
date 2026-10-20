<script setup lang="ts">
import type { ApplicationsAppActions } from '../composables/useApplicationsAppActions'

/**
 * Diálogos de las acciones sobre una aplicación (activar/desactivar, rotar
 * secreto y la modal de un solo uso del secreto). Los comparten el listado y
 * el detalle; el estado viene de `useApplicationsAppActions`.
 */
const props = defineProps<{ actions: ApplicationsAppActions }>()

const toggleApp = computed(() => props.actions.toggle.target)
const deactivating = computed(() => toggleApp.value?.is_active ?? true)
</script>

<template>
  <UiConfirmModal
    v-model:open="actions.toggle.open"
    :title="deactivating ? 'Desactivar aplicación' : 'Activar aplicación'"
    :message="deactivating
      ? `Se desactivará «${toggleApp?.name}». Podrás reactivarla cuando quieras.`
      : `Se activará «${toggleApp?.name}».`"
    :confirm-label="deactivating ? 'Desactivar' : 'Activar'"
    :variant="deactivating ? 'danger' : 'primary'"
    :loading="actions.toggle.loading"
    :error="actions.toggle.error"
    @confirm="actions.toggle.confirm()"
  />

  <UiConfirmModal
    v-model:open="actions.rotate.open"
    title="Rotar secreto"
    :message="`Se generará un nuevo secreto para «${actions.rotate.target?.name}». El actual dejará de funcionar de inmediato y el nuevo se mostrará una sola vez.`"
    confirm-label="Rotar secreto"
    :loading="actions.rotate.loading"
    :error="actions.rotate.error"
    @confirm="actions.rotate.confirm()"
  />

  <ApplicationsSecretModal :reveal="actions.reveal.value" @close="actions.clearReveal()" />
</template>
