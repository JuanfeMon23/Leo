<template>
  <section class="mx-auto flex max-w-lg flex-col items-center gap-4 px-4 py-16 text-center" aria-labelledby="leo-forbidden-title">
    <p class="text-5xl font-bold text-default-300" aria-hidden="true">403</p>
    <h1 id="leo-forbidden-title" class="text-xl font-semibold text-text">No tienes permiso para ver esta página</h1>
    <p class="text-sm text-text-muted">
      Tu usuario no tiene asignada la acción necesaria. Si crees que deberías tener acceso, pide a un
      administrador que te asigne el rol correspondiente.
    </p>
    <UiButton to="/" variant="secondary">Ir al inicio</UiButton>
  </section>
</template>

<script setup lang="ts">
// Página de leo-client (la usa el middleware por tag). Exige sesión, sin tag.
definePageMeta({ leo: {} })
useHead({ title: 'Sin permiso' })
</script>
