<script setup lang="ts">
import { useZodForm } from '#andromeda/composables/useZodForm'
import type { ApplicationActionRead } from '../types/applications'
import { previewActionTag } from '../utils/actionTag'
import { actionCreateSchema } from '../utils/applicationSchemas'

/**
 * Crear (sin `action`) o editar nombre y descripción de una acción. El
 * «Nombre del permiso» es lo que ve quien administra roles; el verbo forma el
 * tag técnico `<app>.<modulo>.<verbo>` (el backend lo arma; aquí solo la vista
 * previa en vivo) y no se edita. Un nombre repetido en el módulo (409
 * `duplicate`) se marca en su campo.
 */
const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{
  appId: string
  appSlug: string
  moduleId: string
  moduleSlug: string
  action?: ApplicationActionRead | null
}>()
const emit = defineEmits<{ saved: [value: ApplicationActionRead] }>()

const api = useApplicationsApi()
const isEdit = computed(() => Boolean(props.action))

const form = useZodForm(actionCreateSchema, {
  initialValues: () => ({ verb: props.action?.verb ?? '', name: props.action?.name ?? '', description: props.action?.description ?? '' }),
  resetOn: open
})

const preview = computed(() => previewActionTag(props.appSlug, props.moduleSlug, String(form.values.verb ?? '')))

const onSubmit = form.submit(async (values) => {
  const saved = props.action
    ? await api.updateAction(props.appId, props.action.id, { name: values.name, description: values.description })
    : await api.createAction(props.appId, props.moduleId, values)
  emit('saved', saved)
  open.value = false
})
</script>

<template>
  <UiFormModal
    v-model:open="open"
    :title="isEdit ? 'Editar acción' : 'Nueva acción'"
    :submit-label="isEdit ? 'Guardar' : 'Crear'"
    :submitting="form.isSubmitting.value"
    :form-error="form.formError.value"
    @submit="onSubmit"
  >
    <UiFormField name="name" label="Nombre del permiso" required hint="Cómo lo verá quien asigne permisos a un rol. Ejemplo: «Consultar muestras».">
      <UiTextInput placeholder="Consultar muestras" />
    </UiFormField>
    <UiFormField name="verb" label="Verbo" required :hint="isEdit ? 'No se puede cambiar: forma parte del tag.' : 'Minúsculas, números y guiones. No se podrá cambiar.'">
      <UiTextInput placeholder="view" :disabled="isEdit" />
    </UiFormField>
    <div class="rounded-lg bg-default-100 px-3 py-2 text-sm">
      <span class="text-text-muted">Tag resultante: </span>
      <code class="break-all font-medium" :class="preview.complete ? 'text-text' : 'text-text-muted'" data-testid="tag-preview">{{ isEdit ? action!.tag : preview.text }}</code>
    </div>
    <UiFormField name="description" label="Descripción">
      <UiTextarea :rows="2" />
    </UiFormField>
  </UiFormModal>
</template>
