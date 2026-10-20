<script setup lang="ts">
import { useZodForm } from '#andromeda/composables/useZodForm'
import type { UserRead } from '../types/users'
import { userEditSchema } from '../utils/userSchemas'

/**
 * Editar los datos personales de un usuario. El usuario (login) es inmutable
 * y la contraseña se cambia aparte (restablecer): aquí no aparecen.
 */
const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ user: UserRead | null }>()
const emit = defineEmits<{ saved: [value: UserRead] }>()

const api = useUsersApi()

const form = useZodForm(userEditSchema, {
  initialValues: () => ({
    email: props.user?.email ?? '',
    first_name: props.user?.first_name ?? '',
    last_name: props.user?.last_name ?? '',
    document_type: props.user?.document_type ?? '',
    document_number: props.user?.document_number ?? ''
  }),
  resetOn: open
})

const onSubmit = form.submit(async (v) => {
  if (!props.user) return
  const saved = await api.update(props.user.id, v)
  emit('saved', saved)
  open.value = false
})
</script>

<template>
  <UiFormModal
    v-model:open="open"
    title="Editar usuario"
    submit-label="Guardar"
    size="lg"
    :submitting="form.isSubmitting.value"
    :form-error="form.formError.value"
    @submit="onSubmit"
  >
    <div class="text-sm">
      <div class="font-medium text-text-muted">Usuario</div>
      <div class="mt-1" data-testid="edit-username"><code>{{ user?.username }}</code> <span class="text-text-muted">(no se puede cambiar)</span></div>
    </div>
    <UsersFormFields />
  </UiFormModal>
</template>
