<script setup lang="ts">
/**
 * Pantalla `/authorize`: valida los parámetros que manda la app (incluido el `dpop_jkt` de la llave de la app, que se reenvía tal cual), comprueba la
 * sesión SSO (sin sesión, al login y de vuelta aquí) y pide el code a Leo. Con
 * éxito navega (top-level) a `redirect_to`. Usa solo la sesión de Leo; no hay
 * tokens en el JS.
 */
const props = defineProps<{
  query: Record<string, unknown>
  /** URL completa de esta pantalla (ruta + query), para volver tras el login. */
  fullPath: string
}>()

type PanelState =
  | { kind: 'working' }
  | { kind: 'invalid', message: string }
  | { kind: 'forbidden', message: string }
  | { kind: 'error', message: string }

const state = ref<PanelState>({ kind: 'working' })
const session = useLeoSession()
const api = useLeoApi()
const { $leo } = useNuxtApp()

async function goToLogin() {
  const location = await $leo.transport.login(props.fullPath)
  await navigateTo(location.url, { external: location.external, replace: true })
}

async function run() {
  state.value = { kind: 'working' }
  const parsed = parseAuthorizeParams(props.query)
  if (!parsed.ok) {
    state.value = { kind: 'invalid', message: parsed.message }
    return
  }
  try {
    await session.ensure()
  } catch (err) {
    state.value = { kind: 'error', message: leoErrorMessage(err) }
    return
  }
  if (!session.isAuthenticated.value) return goToLogin()

  const outcome = await runAuthorize({
    params: parsed.params,
    request: (path, options) => api(path, options)
  })
  if (outcome.status === 'redirect') {
    // Navegación top-level hacia la app: sale de la SPA a propósito.
    window.location.assign(outcome.url)
  } else if (outcome.status === 'login') {
    session.clear()
    await goToLogin()
  } else {
    state.value = { kind: outcome.status, message: outcome.message }
  }
}

onMounted(run)
</script>

<template>
  <UiCard>
    <div v-if="state.kind === 'working'" class="flex flex-col items-center gap-3 py-6 text-text-muted" data-testid="authorize-working">
      <UiSpinner />
      <p>Autorizando acceso…</p>
    </div>

    <div v-else-if="state.kind === 'forbidden'" class="flex flex-col gap-4" data-testid="authorize-forbidden">
      <UiAlert variant="warning" title="Sin acceso" :message="state.message" />
      <p class="text-sm text-text-muted">
        Pide a un administrador que te asigne un rol en esa aplicación.
      </p>
      <UiButton to="/" variant="secondary">Volver al inicio</UiButton>
    </div>

    <div v-else class="flex flex-col gap-4" data-testid="authorize-error">
      <UiAlert variant="danger" title="No se pudo autorizar el acceso" :message="state.message" />
      <div class="flex gap-2">
        <UiButton v-if="state.kind === 'error'" variant="secondary" @click="run">Reintentar</UiButton>
        <UiButton to="/" variant="secondary">Volver al inicio</UiButton>
      </div>
    </div>
  </UiCard>
</template>
