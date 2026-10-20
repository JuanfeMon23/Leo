<script setup lang="ts">
import type { SessionsRevoke } from '../composables/useSessionsRevoke'

/** Confirmación de revocar una sesión; si es la propia, advierte que cerrará la sesión de quien confirma. */
const props = defineProps<{ revoke: SessionsRevoke }>()

const own = computed(() => props.revoke.target?.is_current ?? false)
</script>

<template>
  <UiConfirmModal
    v-model:open="revoke.open"
    :title="own ? 'Cerrar tu propia sesión' : 'Revocar sesión'"
    :message="own
      ? 'Esta es la sesión con la que estás conectado. Si la revocas se cerrará tu sesión de inmediato y tendrás que volver a iniciar sesión.'
      : 'La sesión dejará de funcionar de inmediato y su dueño tendrá que volver a iniciar sesión. Esta acción no se puede deshacer.'"
    :confirm-label="own ? 'Cerrar mi sesión' : 'Revocar'"
    variant="danger"
    :loading="revoke.loading"
    :error="revoke.error"
    @confirm="revoke.confirm()"
  />
</template>
