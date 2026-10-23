<script setup lang="ts">
import { useZodForm } from '#andromeda/composables/useZodForm'
import type { UserRead } from '../types/users'
import { userCreateSchema } from '../utils/userSchemas'

/**
 * Crear un usuario. Los errores de campo del backend (usuario, correo o
 * documento repetidos, contraseña débil) se marcan en su campo con el mensaje
 * del backend. La contraseña solo vive en el campo: se limpia al cerrar.
 */
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [value: UserRead] }>()

const api = useUsersApi()
const { policy } = usePasswordPolicy()

const form = useZodForm(userCreateSchema(() => policy.value), {
  initialValues: () => ({
    username: '', email: '', first_name: '', last_name: '', document_type: '', document_number: '', password: ''
  }),
  resetOn: open
})
watch(open, (isOpen) => { if (!isOpen) form.reset() })

const values = form.values as { password?: string }

const onSubmit = form.submit(async (v) => {
  const saved = await api.create(v)
  emit('saved', saved)
  open.value = false
})
</script>

<template>
  <UiFormModal
    v-model:open="open"
    title="Nuevo usuario"
    submit-label="Crear usuario"
    size="lg"
    :submitting="form.isSubmitting.value"
    :form-error="form.formError.value"
    @submit="onSubmit"
  >
    <UiFormField name="username" label="Usuario" required hint="3 a 64 caracteres, en minúsculas, sin «@». Con él inicia sesión y no se podrá cambiar.">
      <UiTextInput placeholder="ana.perez" autocomplete="off" />
    </UiFormField>
    <UsersFormFields />
    <UiFormField name="password" label="Contraseña inicial" required>
      <UiPasswordInput autocomplete="new-password" />
    </UiFormField>
    <UiPasswordRequirements :password="values.password ?? ''" :policy="policy" />
  </UiFormModal>
</template>
