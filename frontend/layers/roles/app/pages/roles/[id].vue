<script setup lang="ts">
definePageMeta({ leo: { tag: 'leo.roles.view' } })
useHead({ title: 'Rol · Leo' })

const route = useRoute()
const id = computed(() => String(route.params.id))
</script>

<template>
  <RolesDetail :id="id" />
</template>
