<template>
  <section class="mx-auto flex max-w-md flex-col items-center gap-4 px-4 py-16 text-center" aria-live="polite">
    <template v-if="error">
      <h1 class="text-xl font-semibold text-text">No se pudo iniciar sesión</h1>
      <p class="text-sm text-text-muted" role="alert" data-testid="leo-callback-error">{{ error }}</p>
      <UiButton :loading="retrying" @click="retry">Iniciar sesión de nuevo</UiButton>
    </template>
    <template v-else>
      <h1 class="text-xl font-semibold text-text">Iniciando sesión…</h1>
      <p class="text-sm text-text-muted">Un momento, estamos verificando tu acceso.</p>
    </template>
  </section>
</template>

<script setup lang="ts">
/**
 * Retorno de Leo en el transporte `bff` (ruta `runtimeConfig.public.leo.callbackPath`,
 * registrada por `modules/callbackRoute.ts`): llama a `{backend}/auth/callback?code&state`
 * con DPoP, el backend fija las cookies de sesión y se vuelve a la ruta de origen.
 * Pública y tolerante a la doble ejecución (el transporte canjea el code una sola vez).
 */
import { leoErrorMessage } from '../lib/errors'

definePageMeta({ leo: { public: true } })
useHead({ title: 'Iniciando sesión' })

const route = useRoute()
const session = useLeoSession()
const { $leo } = useNuxtApp()

const error = ref('')
const retrying = ref(false)

const first = (value: unknown) => (Array.isArray(value) ? value[0] : value)
const asString = (value: unknown) => (typeof value === 'string' ? value : '')

async function finish() {
  const code = asString(first(route.query.code))
  const state = asString(first(route.query.state))
  if (first(route.query.error) || !code || !state || !$leo.transport.completeLogin) {
    error.value = 'El inicio de sesión no se completó. Inténtalo de nuevo.'
    return
  }
  try {
    const { me, returnTo } = await $leo.transport.completeLogin({ code, state })
    session.setMe(me)
    await navigateTo(returnTo, { replace: true })
  } catch (err) {
    error.value = leoErrorMessage(err)
  }
}

async function retry() {
  retrying.value = true
  try {
    await session.redirectToLogin(undefined, '/')
  } catch (err) {
    error.value = leoErrorMessage(err)
  } finally {
    retrying.value = false
  }
}

onMounted(finish)
</script>
