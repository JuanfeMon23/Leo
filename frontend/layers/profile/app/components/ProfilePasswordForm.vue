<script setup lang="ts">
import { useZodForm } from '#andromeda/composables/useZodForm'
import { passwordChangeSchema } from '../utils/profileSchemas'
import { profilePasswordErrors } from '../utils/profileErrors'

/**
 * Cambiar la contraseña propia. Valida la política del backend en vivo
 * (`UiPasswordRequirements`), pide confirmación (se cierran las demás
 * sesiones) y mapea los errores del backend a su campo. Las contraseñas solo
 * viven en los campos: nunca se persisten ni se muestran, y se limpian al
 * terminar o al salir de la página.
 */
const session = useLeoSession()
const api = useProfileApi()
const toast = useToast()

const user = computed(() => session.user.value)

// La política depende del usuario y del correo ACTUALES (se leen en cada validación,
// así un cambio de correo hecho en esta misma página se respeta).
const form = useZodForm(passwordChangeSchema(() => ({ username: user.value?.username, email: user.value?.email })), {
  initialValues: () => ({ current_password: '', new_password: '', confirm_password: '' })
})
const values = form.values as { current_password?: string, new_password?: string, confirm_password?: string }

const confirmOpen = ref(false)
const confirming = ref(false)
const success = ref(false)

// Valida primero; solo entonces pide confirmar (nada se envía todavía).
const onSubmit = form.submit(() => {
  success.value = false
  confirmOpen.value = true
})

async function onConfirm() {
  confirming.value = true
  try {
    await api.changePassword({
      current_password: values.current_password ?? '',
      new_password: values.new_password ?? ''
    })
    confirmOpen.value = false
    form.reset()
    success.value = true
    toast.success('Contraseña actualizada')
  } catch (err) {
    confirmOpen.value = false
    const mapped = profilePasswordErrors(err)
    form.formError.value = mapped.form
    for (const [field, message] of Object.entries(mapped.fields)) {
      form.setFieldError(field as 'current_password' | 'new_password', message)
    }
    // La contraseña actual rechazada se vuelve a pedir; no queda en el campo.
    if (mapped.fields.current_password) form.setFieldValue('current_password', '', false)
  } finally {
    confirming.value = false
  }
}

onBeforeUnmount(() => form.reset())
</script>

<template>
  <UiCard title="Cambiar contraseña" description="Elige una contraseña que no uses en otro sitio.">
    <form class="flex flex-col gap-4" novalidate data-testid="password-form" @submit.prevent="onSubmit">
      <UiAlert v-if="success" variant="success" message="Contraseña actualizada. Se cerraron tus otras sesiones." data-testid="password-success" />
      <UiAlert v-if="form.formError.value" variant="danger" :message="form.formError.value" data-testid="password-error" />

      <UiFormField name="current_password" label="Contraseña actual" required>
        <UiPasswordInput autocomplete="current-password" />
      </UiFormField>
      <UiFormField name="new_password" label="Contraseña nueva" required>
        <UiPasswordInput autocomplete="new-password" />
      </UiFormField>
      <UiPasswordRequirements :password="values.new_password ?? ''" :username="user?.username" :email="user?.email" />
      <UiFormField name="confirm_password" label="Confirmar contraseña nueva" required>
        <UiPasswordInput autocomplete="new-password" />
      </UiFormField>

      <div>
        <UiButton type="submit" :loading="form.isSubmitting.value" data-testid="password-save">
          Cambiar contraseña
        </UiButton>
      </div>
    </form>

    <UiConfirmModal
      v-model:open="confirmOpen"
      title="Cambiar contraseña"
      message="Al cambiar tu contraseña se cerrarán tus demás sesiones abiertas (otros dispositivos y navegadores). Esta sesión se mantiene."
      confirm-label="Cambiar contraseña"
      variant="primary"
      :loading="confirming"
      @confirm="onConfirm"
    />
  </UiCard>
</template>
