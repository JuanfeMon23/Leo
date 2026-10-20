<script setup lang="ts">
import { useZodForm } from '#andromeda/composables/useZodForm'
import type { ApplicationModuleRead } from '../types/applications'
import { moduleCreateSchema } from '../utils/applicationSchemas'

/** Crear (sin `module`) o editar un módulo de una app. El slug no se edita. */
const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ appId: string, module?: ApplicationModuleRead | null }>()
const emit = defineEmits<{ saved: [value: ApplicationModuleRead] }>()

const api = useApplicationsApi()
const isEdit = computed(() => Boolean(props.module))

const form = useZodForm(moduleCreateSchema, {
  initialValues: () => ({
    slug: props.module?.slug ?? '',
    name: props.module?.name ?? '',
    description: props.module?.description ?? ''
  }),
  resetOn: open
})

const onSubmit = form.submit(async (values) => {
  const saved = props.module
    ? await api.updateModule(props.appId, props.module.id, { name: values.name, description: values.description })
    : await api.createModule(props.appId, values)
  emit('saved', saved)
  open.value = false
})
</script>

<template>
  <UiFormModal
    v-model:open="open"
    :title="isEdit ? 'Editar módulo' : 'Nuevo módulo'"
    :submit-label="isEdit ? 'Guardar' : 'Crear'"
    :submitting="form.isSubmitting.value"
    :form-error="form.formError.value"
    @submit="onSubmit"
  >
    <UiFormField name="slug" label="Identificador (slug)" required :hint="isEdit ? 'No se puede cambiar: forma parte de los tags.' : 'Minúsculas, números y guiones. No se podrá cambiar.'">
      <UiTextInput placeholder="samples" :disabled="isEdit" />
    </UiFormField>
    <UiFormField name="name" label="Nombre" required>
      <UiTextInput />
    </UiFormField>
    <UiFormField name="description" label="Descripción">
      <UiTextarea :rows="2" />
    </UiFormField>
  </UiFormModal>
</template>
