<script setup lang="ts">
definePageMeta({ leo: { tag: 'leo.settings.view' } })
useHead({ title: 'Ajustes del sistema · Leo' })

const admin = useSettingsScreen()
</script>

<template>
  <UiSettingsPanel :admin="admin" />
</template>
