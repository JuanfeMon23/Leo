<script setup lang="ts">
import { useZodForm } from '#andromeda/composables/useZodForm'
import type { LeoUser } from '#leo-client/lib/types'
import type { ProfileUpdatePayload } from '../types/profile'
import { profileUpdateFieldError } from '../utils/profileErrors'
import { profileFormSchema } from '../utils/profileSchemas'

/**
 * Datos personales de la persona con sesión: usuario (solo lectura) y
 * nombres, apellidos y correo editables. Al guardar se actualiza el estado de
 * sesión local con la respuesta, así la barra superior muestra el nombre
 * nuevo sin recargar. Los errores de campo del backend (correo repetido, 422)
 * se marcan en su campo.
 */
const session = useLeoSession()
const api = useProfileApi()
const toast = useToast()

const user = computed(() => session.user.value)

const toValues = (u: LeoUser | null) => ({
  first_name: u?.first_name ?? '',
  last_name: u?.last_name ?? '',
  email: u?.email ?? ''
})

const form = useZodForm(profileFormSchema(() => user.value?.email ?? ''), {
  initialValues: () => ({ ...toValues(user.value), current_password: '' })
})
const values = form.values as { first_name?: string, last_name?: string, email?: string, current_password?: string }

/** Solo los campos que cambiaron (comparados ya recortados). */
const changes = computed<ProfileUpdatePayload>(() => {
  const current = toValues(user.value)
  const out: ProfileUpdatePayload = {}
  for (const key of ['first_name', 'last_name', 'email'] as const) {
    const next = (values[key] ?? '').trim()
    if (next !== current[key]) out[key] = next
  }
  return out
})
const dirty = computed(() => Object.keys(changes.value).length > 0)
// «Contraseña actual» solo se pide (y se envía) si el correo cambió.
const emailChanged = computed(() => changes.value.email !== undefined)

const onSubmit = form.submit(async () => {
  const body: ProfileUpdatePayload = { ...changes.value }
  if (emailChanged.value) body.current_password = values.current_password ?? ''
  try {
    const me = await api.update(body)
    session.setMe(me)
    form.reset({ ...toValues(me.user), current_password: '' })
    toast.success('Datos actualizados')
  } catch (err) {
    const message = profileUpdateFieldError(err)
    if (!message) throw err
    form.setFieldError('current_password', message)
    // La contraseña rechazada no queda en el campo.
    form.setFieldValue('current_password', '', false)
  }
})

onBeforeUnmount(() => form.reset())
</script>

<template>
  <UiCard title="Datos personales" description="Tu nombre y tu correo se muestran en la barra superior de todas las aplicaciones.">
    <form class="flex flex-col gap-4" novalidate data-testid="profile-form" @submit.prevent="onSubmit">
      <UiAlert v-if="form.formError.value" variant="danger" :message="form.formError.value" data-testid="profile-error" />

      <div class="text-sm">
        <div class="font-medium text-text-muted">Usuario</div>
        <div class="mt-1" data-testid="profile-username"><code>{{ user?.username }}</code> <span class="text-text-muted">(no se puede cambiar)</span></div>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <UiFormField name="first_name" label="Nombres" required>
          <UiTextInput autocomplete="given-name" />
        </UiFormField>
        <UiFormField name="last_name" label="Apellidos" required>
          <UiTextInput autocomplete="family-name" />
        </UiFormField>
      </div>
      <UiFormField name="email" label="Correo electrónico" required>
        <UiTextInput type="email" autocomplete="email" />
      </UiFormField>
      <UiFormField v-if="emailChanged" name="current_password" label="Contraseña actual" hint="Necesaria para confirmar el cambio de correo." required>
        <UiPasswordInput autocomplete="current-password" />
      </UiFormField>

      <div>
        <UiButton type="submit" :loading="form.isSubmitting.value" :disabled="!dirty" data-testid="profile-save">
          Guardar cambios
        </UiButton>
      </div>
    </form>
  </UiCard>
</template>
