<script setup lang="ts">
import { useZodForm } from '#andromeda/composables/useZodForm'
import type { ApplicationCreated, ApplicationRead } from '../types/applications'
import { applicationCreateSchema, redirectUrisToText } from '../utils/applicationSchemas'

/**
 * Crear (sin `application`) o editar una aplicación. El slug (= client_id)
 * solo se escribe al crear: al editar se muestra bloqueado. Al crear, emite
 * `created` con el `client_secret` en claro (lo muestra la modal de un solo uso).
 */
const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ application?: ApplicationRead | null }>()
const emit = defineEmits<{ created: [value: ApplicationCreated], updated: [value: ApplicationRead] }>()

const api = useApplicationsApi()
const isEdit = computed(() => Boolean(props.application))

const form = useZodForm(applicationCreateSchema, {
  initialValues: () => ({
    slug: props.application?.slug ?? '',
    name: props.application?.name ?? '',
    description: props.application?.description ?? '',
    base_url: props.application?.base_url ?? '',
    redirect_uris: redirectUrisToText(props.application?.redirect_uris ?? [])
  }),
  resetOn: open
})

const onSubmit = form.submit(async (values) => {
  if (props.application) {
    const { slug: _slug, ...changes } = values
    emit('updated', await api.update(props.application.id, changes))
  } else {
    emit('created', await api.create(values))
  }
  open.value = false
})
</script>

<template>
  <UiFormModal
    v-model:open="open"
    :title="isEdit ? 'Editar aplicación' : 'Nueva aplicación'"
    :submit-label="isEdit ? 'Guardar' : 'Crear'"
    :submitting="form.isSubmitting.value"
    :form-error="form.formError.value"
    size="lg"
    @submit="onSubmit"
  >
    <UiFormField name="slug" label="Identificador (slug)" required :hint="isEdit ? 'No se puede cambiar: es el client_id.' : 'Minúsculas, números y guiones. No se podrá cambiar.'">
      <UiTextInput placeholder="mi-app" :disabled="isEdit" />
    </UiFormField>
    <UiFormField name="name" label="Nombre" required>
      <UiTextInput />
    </UiFormField>
    <UiFormField name="description" label="Descripción">
      <UiTextarea :rows="2" />
    </UiFormField>
    <UiFormField name="base_url" label="URL base" required>
      <UiTextInput type="url" placeholder="https://mi-app.example.com" />
    </UiFormField>
    <UiFormField name="redirect_uris" label="Redirect URIs" hint="Una por línea. Deben coincidir exactamente con las que usa la app al iniciar sesión.">
      <UiTextarea :rows="4" placeholder="https://mi-app.example.com/callback" />
    </UiFormField>
  </UiFormModal>
</template>
