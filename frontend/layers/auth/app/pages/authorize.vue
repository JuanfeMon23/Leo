<script setup lang="ts">
// Pública a propósito: maneja ella misma la sesión (sin sesión va a /login y vuelve),
// así el middleware global no la mete en un bucle.
definePageMeta({ layout: 'blank', leo: { public: true } })
useHead({ title: 'Autorizar acceso · Leo' })

const route = useRoute()
</script>

<template>
  <AuthAuthorizePanel :query="route.query" :full-path="route.fullPath" />
</template>
