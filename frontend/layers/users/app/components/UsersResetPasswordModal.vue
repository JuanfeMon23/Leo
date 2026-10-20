<script setup lang="ts">
import { useZodForm } from '#andromeda/composables/useZodForm'
import type { UserRead } from '../types/users'
import { usersFullName } from '../utils/userDisplay'
import { passwordResetSchema } from '../utils/userSchemas'

/**
 * Asignar una contraseña nueva a un usuario (misma política que al crear).
 * Cierra todas sus sesiones abiertas. La contraseña solo vive en el campo:
 * se limpia al cerrar y nunca se muestra ni se guarda.
 */
const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ user: UserRead }>()
const emit = defineEmits<{ saved: [value: UserRead] }>()

const api = useUsersApi()
const toast = useToast()

const form = useZodForm(passwordResetSchema({ username: props.user.username, email: props.user.email }), {
  initialValues: () => ({ password: '' }),
  resetOn: open
})
watch(open, (isOpen) => { if (!isOpen) form.reset() })

const values = form.values as { password?: string }

const onSubmit = form.submit(async (v) => {
  const saved = await api.resetPassword(props.user.id, v.password)
  toast.success(`Contraseña de «${usersFullName(props.user)}» actualizada. Sus sesiones abiertas se cerraron.`)
  emit('saved', saved)
  open.value = false
})
</script>

<template>
  <UiFormModal
    v-model:open="open"
    title="Restablecer contraseña"
    submit-label="Asignar contraseña"
    :submitting="form.isSubmitting.value"
    :form-error="form.formError.value"
    @submit="onSubmit"
  >
    <UiAlert variant="warning" data-testid="reset-warning">
      Se cerrarán todas las sesiones abiertas de {{ usersFullName(user) }}: tendrá que iniciar sesión de nuevo con la contraseña nueva.
    </UiAlert>
    <UiFormField name="password" label="Contraseña nueva" required>
      <UiTextInput type="password" autocomplete="new-password" />
    </UiFormField>
    <UsersPasswordRequirements :password="values.password ?? ''" :username="user.username" :email="user.email" />
  </UiFormModal>
</template>
