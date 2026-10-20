<script setup lang="ts">
definePageMeta({ leo: { tag: 'leo.applications.view' } })
useHead({ title: 'Aplicación · Leo' })

const route = useRoute()
const id = computed(() => String(route.params.id))
</script>

<template>
  <ApplicationsDetail :id="id" />
</template>
