<script setup lang="ts">
// No hay tag `view`: la pantalla se ve con cualquiera de las acciones de gestión.
definePageMeta({
  leo: { tag: ['leo.document-types.create', 'leo.document-types.edit', 'leo.document-types.deactivate'], mode: 'any' }
})
useHead({ title: 'Tipos de documento · Leo' })
</script>

<template>
  <DocumentTypesList />
</template>
