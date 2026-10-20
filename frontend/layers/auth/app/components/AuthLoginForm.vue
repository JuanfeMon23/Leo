<script setup lang="ts">
import type { LeoMe } from '#leo-client/lib/types'
import { safeReturnTo } from '#leo-client/lib/returnTo'
import { useZodForm } from '#andromeda/composables/useZodForm'

/**
 * Formulario de login de Leo: usuario o email + contraseña. Tras
 * `POST /auth/login` guarda la sesión y vuelve a `redirect` (solo rutas
 * internas) o al inicio. `reason` (`idle`/`expired`) explica por qué se cerró
 * la sesión anterior.
 */
const props = defineProps<{
  redirect?: unknown
  reason?: unknown
}>()

const api = useLeoApi()
const session = useLeoSession()

const form = useZodForm(loginSchema, { initialValues: { login: '', password: '' } })
const reasonMessage = computed(() => loginReasonMessage(props.reason))
const target = computed(() => safeReturnTo(props.redirect))

const onSubmit = form.submit(async (values) => {
  try {
    const me = await api<LeoMe>('/auth/login', { method: 'POST', body: values, skipSessionHandling: true })
    session.setMe(me)
  } catch (err) {
    // Mensaje propio (429 con tiempo restante); nunca la respuesta cruda.
    form.formError.value = loginErrorMessage(err)
    form.setFieldValue('password', '')
    return
  }
  await navigateTo(target.value, { replace: true })
})
</script>

<template>
  <UiCard title="Iniciar sesión" description="Ingresa con tu usuario o correo electrónico.">
    <form class="flex flex-col gap-4" novalidate @submit.prevent="onSubmit">
      <UiAlert v-if="reasonMessage" variant="info" :message="reasonMessage" data-testid="login-reason" />
      <UiAlert v-if="form.formError.value" variant="danger" :message="form.formError.value" data-testid="login-error" />

      <UiFormField name="login" label="Usuario o correo electrónico" required>
        <UiTextInput placeholder="usuario o correo" autocomplete="username" />
      </UiFormField>
      <UiFormField name="password" label="Contraseña" required>
        <UiTextInput type="password" autocomplete="current-password" />
      </UiFormField>

      <UiButton type="submit" :loading="form.isSubmitting.value" class="w-full">
        Iniciar sesión
      </UiButton>
    </form>
  </UiCard>
</template>
