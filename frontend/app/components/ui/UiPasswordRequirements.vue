<script setup lang="ts">
/**
 * Requisitos de la contraseña con el cumplimiento en vivo (misma política que
 * el backend). Solo lee el valor para calcular; no lo guarda ni lo muestra.
 */
const props = defineProps<{
  password: string
  username?: string
  email?: string
}>()

const requirements = computed(() =>
  passwordRequirements(props.password ?? '', { username: props.username, email: props.email })
)
</script>

<template>
  <ul class="space-y-1 text-sm" aria-label="Requisitos de la contraseña" data-testid="password-requirements">
    <li
      v-for="req in requirements"
      :key="req.id"
      class="flex items-center gap-2"
      :class="req.met ? 'text-success-700' : 'text-text-muted'"
      :data-met="req.met"
      data-testid="password-requirement"
    >
      <svg class="h-4 w-4 shrink-0" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path v-if="req.met" d="M4 10.5l4 4 8-9" stroke-linecap="round" stroke-linejoin="round" />
        <circle v-else cx="10" cy="10" r="6" />
      </svg>
      <span>{{ req.label }}</span>
      <span class="sr-only">{{ req.met ? '(cumplido)' : '(pendiente)' }}</span>
    </li>
  </ul>
</template>
