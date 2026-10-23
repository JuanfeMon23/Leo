<script setup lang="ts">
// Neutra a propósito: no lista qué existe en el panel. Exige sesión, sin tag.
definePageMeta({ layout: 'blank', leo: {} })
useHead({ title: 'Sin acceso · Leo' })

const session = useLeoSession()
const loggingOut = ref(false)

async function logout() {
  loggingOut.value = true
  try {
    await session.logout()
  } finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <UiCard title="Sin acceso al panel" description="Tu cuenta no tiene acceso a esta aplicación.">
    <div class="flex flex-wrap gap-3">
      <UiButton to="/profile" variant="secondary" data-testid="no-access-profile">Mi perfil</UiButton>
      <UiButton variant="ghost" :loading="loggingOut" data-testid="no-access-logout" @click="logout">Cerrar sesión</UiButton>
    </div>
  </UiCard>
</template>
