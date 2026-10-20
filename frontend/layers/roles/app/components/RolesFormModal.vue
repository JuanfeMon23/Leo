<script setup lang="ts">
import { activeSelectOptions } from '#andromeda/utils/activeOptions'
import { useZodForm } from '#andromeda/composables/useZodForm'
import type { RoleRead, RolesApplication } from '../types/roles'
import { roleCreateSchema } from '../utils/roleSchemas'

/**
 * Crear (sin `role`) o editar un rol. La aplicación y el identificador (slug)
 * solo se eligen al crear: al editar se muestran bloqueados. Un slug repetido
 * en la aplicación (409 `duplicate`) se marca en su campo.
 */
const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{
  role?: RoleRead | null
  applications: RolesApplication[]
  /** Aplicación preseleccionada al crear (p. ej. la del filtro del listado). */
  defaultApplicationId?: string
}>()
const emit = defineEmits<{ saved: [value: RoleRead] }>()

const api = useRolesApi()
const isEdit = computed(() => Boolean(props.role))

const form = useZodForm(roleCreateSchema, {
  initialValues: () => ({
    application_id: props.role?.application_id ?? props.defaultApplicationId ?? '',
    slug: props.role?.slug ?? '',
    name: props.role?.name ?? '',
    description: props.role?.description ?? ''
  }),
  resetOn: open
})

const appOptions = computed(() =>
  activeSelectOptions(props.applications, a => a.name, props.role?.application_id)
)

const onSubmit = form.submit(async (values) => {
  const saved = props.role
    ? await api.update(props.role.id, { name: values.name, description: values.description })
    : await api.create(values)
  emit('saved', saved)
  open.value = false
})
</script>

<template>
  <UiFormModal
    v-model:open="open"
    :title="isEdit ? 'Editar rol' : 'Nuevo rol'"
    :submit-label="isEdit ? 'Guardar' : 'Crear'"
    :submitting="form.isSubmitting.value"
    :form-error="form.formError.value"
    @submit="onSubmit"
  >
    <UiFormField name="application_id" label="Aplicación" required :hint="isEdit ? 'No se puede cambiar: el rol agrupa permisos de esta aplicación.' : 'El rol solo podrá tener permisos de esta aplicación.'">
      <UiSelect :options="appOptions" placeholder="Elige una aplicación" :disabled="isEdit" />
    </UiFormField>
    <UiFormField name="slug" label="Identificador (slug)" required :hint="isEdit ? 'No se puede cambiar.' : 'Minúsculas, números y guiones. No se podrá cambiar.'">
      <UiTextInput placeholder="analista-de-laboratorio" :disabled="isEdit" />
    </UiFormField>
    <UiFormField name="name" label="Nombre" required>
      <UiTextInput placeholder="Analista de laboratorio" />
    </UiFormField>
    <UiFormField name="description" label="Descripción">
      <UiTextarea :rows="2" />
    </UiFormField>
  </UiFormModal>
</template>
