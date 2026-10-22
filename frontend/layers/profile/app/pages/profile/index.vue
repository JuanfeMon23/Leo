<script setup lang="ts">
// Autogestión: toda persona con sesión, sin tag (el backend tampoco pide `leo.*`).
definePageMeta({ leo: {} })
useHead({ title: 'Mi perfil · Leo' })

const route = useRoute()
</script>

<template>
  <div class="mx-auto flex max-w-2xl flex-col gap-6">
    <ProfileReturnLink :return-param="route.query.return" />
    <UiPageHeader title="Mi perfil" description="Consulta y edita tu información personal y cambia tu contraseña." />
    <ProfilePersonalForm />
    <ProfilePasswordForm />
  </div>
</template>
