<script setup lang="ts">
import { toSelectOptions } from '#andromeda/utils/zodFields'
import { USERS_DOCUMENT_TYPES } from '../types/users'
import { USERS_DOCUMENT_LABELS } from '../utils/userSchemas'

/**
 * Campos de persona (nombres, correo, documento) que comparten crear y editar.
 * Se montan dentro de un `useZodForm` del ancestro (los `UiFormField name`
 * se enlazan solos).
 */
const documentOptions = toSelectOptions(
  Object.fromEntries(USERS_DOCUMENT_TYPES.map(t => [t, `${t} · ${USERS_DOCUMENT_LABELS[t]}`])) as Record<string, string>
)
</script>

<template>
  <div class="grid gap-4 sm:grid-cols-2">
    <UiFormField name="first_name" label="Nombres" required>
      <UiTextInput placeholder="Ana María" />
    </UiFormField>
    <UiFormField name="last_name" label="Apellidos" required>
      <UiTextInput placeholder="Pérez Gómez" />
    </UiFormField>
  </div>
  <UiFormField name="email" label="Correo electrónico" required>
    <UiTextInput type="email" placeholder="ana.perez@empresa.co" />
  </UiFormField>
  <div class="grid gap-4 sm:grid-cols-[2fr_3fr]">
    <UiFormField name="document_type" label="Tipo de documento" required>
      <UiSelect :options="documentOptions" placeholder="Elige el tipo" />
    </UiFormField>
    <UiFormField name="document_number" label="Número de documento" required hint="Sin puntos ni espacios. Las letras se guardan en mayúsculas.">
      <UiTextInput placeholder="1234567890" />
    </UiFormField>
  </div>
</template>
