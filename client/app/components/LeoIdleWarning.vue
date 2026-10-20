<script setup lang="ts">
/**
 * Aviso previo al cierre por inactividad, con cuenta regresiva y "Seguir
 * conectado". Lo incluye `LeoTopBar`; también se puede montar suelto.
 */
const { state, stayConnected } = useLeoIdle()
const session = useLeoSession()

const now = ref(Date.now())
let ticker: ReturnType<typeof setInterval> | undefined

watch(() => state.value.warning, (warning) => {
  if (ticker) clearInterval(ticker)
  ticker = undefined
  if (warning) {
    now.value = Date.now()
    ticker = setInterval(() => { now.value = Date.now() }, 1000)
  }
}, { immediate: true })
onBeforeUnmount(() => ticker && clearInterval(ticker))

const seconds = computed(() => Math.max(0, Math.ceil((state.value.deadline - now.value) / 1000)))
const open = computed({
  get: () => state.value.warning,
  set: (value: boolean) => { if (!value) stayConnected() }
})
</script>

<template>
  <UiModal v-model:open="open" title="¿Sigues ahí?" size="sm" :dismissable="false" hide-close-button>
    <p class="text-sm text-text" role="timer" aria-live="polite">
      Por seguridad, tu sesión se cerrará por inactividad en
      <strong>{{ seconds }} {{ seconds === 1 ? 'segundo' : 'segundos' }}</strong>.
    </p>
    <div class="mt-5 flex justify-end gap-2">
      <UiButton variant="secondary" @click="session.logout()">Cerrar sesión</UiButton>
      <UiButton @click="stayConnected()">Seguir conectado</UiButton>
    </div>
  </UiModal>
</template>
