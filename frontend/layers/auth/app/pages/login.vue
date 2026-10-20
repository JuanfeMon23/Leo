<script setup lang="ts">
import { safeReturnTo } from '#leo-client/lib/returnTo'

definePageMeta({ layout: 'blank', leo: { public: true } })
useHead({ title: 'Iniciar sesión · Leo' })

const route = useRoute()
const session = useLeoSession()

// Quien ya tiene sesión no necesita el formulario: va a su destino.
onMounted(async () => {
  try {
    await session.ensure()
  } catch {
    return // sin servidor se queda el formulario; el envío mostrará el error legible
  }
  if (session.isAuthenticated.value) {
    await navigateTo(safeReturnTo(route.query.redirect), { replace: true })
  }
})
</script>

<template>
  <AuthLoginForm :redirect="route.query.redirect" :reason="route.query.reason" />
</template>
