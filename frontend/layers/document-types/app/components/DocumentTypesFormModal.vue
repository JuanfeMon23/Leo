<script setup lang="ts">
import { useZodForm } from '#andromeda/composables/useZodForm'
import type { DocumentTypeRead } from '../types/documentTypes'
import { documentTypeCreateSchema } from '../utils/documentTypeSchemas'

/**
 * Crear (sin `type`) o editar un tipo de documento. El código solo se elige al
 * crear: al editar se muestra bloqueado. Un código repetido (409 `duplicate`)
 * se marca en su campo.
 */
const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ type?: DocumentTypeRead | null }>()
const emit = defineEmits<{ saved: [value: DocumentTypeRead] }>()

const api = useDocumentTypesApi()
const isEdit = computed(() => Boolean(props.type))

const form = useZodForm(documentTypeCreateSchema, {
  initialValues: () => ({
    code: props.type?.code ?? '',
    name: props.type?.name ?? '',
    sort_order: props.type ? String(props.type.sort_order) : ''
  }),
  resetOn: open
})

const onSubmit = form.submit(async (values) => {
  const saved = props.type
    ? await api.update(props.type.code, { name: values.name, sort_order: values.sort_order })
    : await api.create(values)
  emit('saved', saved)
  open.value = false
})
</script>

<template>
  <UiFormModal
    v-model:open="open"
    :title="isEdit ? 'Editar tipo de documento' : 'Nuevo tipo de documento'"
    :submit-label="isEdit ? 'Guardar' : 'Crear'"
    :submitting="form.isSubmitting.value"
    :form-error="form.formError.value"
    @submit="onSubmit"
  >
    <UiFormField name="code" label="Código" required :hint="isEdit ? 'No se puede cambiar.' : 'Abreviatura corta, p. ej. CC. No se podrá cambiar.'">
      <UiTextInput placeholder="CC" :disabled="isEdit" />
    </UiFormField>
    <UiFormField name="name" label="Nombre" required>
      <UiTextInput placeholder="Cédula de ciudadanía" />
    </UiFormField>
    <UiFormField name="sort_order" label="Orden" required hint="Posición en las listas: menor número, primero.">
      <UiTextInput type="number" placeholder="10" />
    </UiFormField>
  </UiFormModal>
</template>
