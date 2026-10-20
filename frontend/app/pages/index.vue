<script setup lang="ts">
useHead({ title: 'Inicio · Leo' })
const user = useLeoUser()
const name = computed(() => (user.value ? `${user.value.first_name} ${user.value.last_name}`.trim() || user.value.username : ''))
</script>

<template>
  <UiPageHeader title="Inicio" description="Administración de acceso del ecosistema." />
  <UiCard>
    <p data-testid="welcome">Bienvenido{{ name ? `, ${name}` : '' }}.</p>
  </UiCard>
</template>
