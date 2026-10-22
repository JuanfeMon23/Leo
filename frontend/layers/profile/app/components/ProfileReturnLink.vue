<script setup lang="ts">
import { safeReturnUrl } from '../utils/returnUrl'

/**
 * Enlace «Volver a <app>» cuando la URL trae `?return=`. Solo se muestra si el
 * origen coincide con el `base_url` de una app a la que la persona tiene
 * acceso (evita redirecciones abiertas); si no, no se muestra nada.
 */
const props = defineProps<{ returnParam?: unknown }>()

const session = useLeoSession()
const target = computed(() => safeReturnUrl(props.returnParam, session.applications.value))
</script>

<template>
  <a
    v-if="target"
    :href="target.url"
    rel="noopener"
    class="inline-flex items-center gap-1 rounded-md text-sm font-medium text-primary-700 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
    data-testid="profile-return"
  >
    <span aria-hidden="true">←</span> Volver a {{ target.app.name }}
  </a>
</template>
