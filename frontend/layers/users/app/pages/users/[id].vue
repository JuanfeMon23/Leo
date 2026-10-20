<script setup lang="ts">
definePageMeta({ leo: { tag: 'leo.users.view' } })
useHead({ title: 'Usuario · Leo' })

const route = useRoute()
const id = computed(() => String(route.params.id))
</script>

<template>
  <UsersDetail :id="id" />
</template>
