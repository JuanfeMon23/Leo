<script setup lang="ts">
// Pantallas sin sesión (login, authorize): tarjeta centrada con la marca de Leo.
const config = useRuntimeConfig().public.leo
</script>

<template>
  <div class="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-4 py-10 text-text">
    <h1 class="text-2xl font-semibold">{{ config.appName || 'Leo' }}</h1>
    <main class="w-full max-w-md">
      <slot />
    </main>
  </div>
</template>
