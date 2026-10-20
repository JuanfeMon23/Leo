<script setup lang="ts">
import type { UserDetail } from '../types/users'
import { userErrorMessage } from '../utils/userErrors'

/**
 * Selector «Aplicación → Rol» para asignar un rol activo al usuario. Las
 * opciones ya excluyen los roles que tiene. El backend devuelve el detalle
 * actualizado (`assigned`). Va dentro de `LeoCan leo.users.assign-roles`.
 */
const props = defineProps<{
  userId: string
  options: Array<{ value: string, label: string }>
}>()
const emit = defineEmits<{ assigned: [detail: UserDetail] }>()

const api = useUsersApi()
const toast = useToast()

const roleId = ref('')
const saving = ref(false)
const error = ref<string | null>(null)

async function assign() {
  if (!roleId.value) return
  saving.value = true
  error.value = null
  try {
    const label = props.options.find(o => o.value === roleId.value)?.label ?? 'el rol'
    const detail = await api.addRoles(props.userId, [roleId.value])
    roleId.value = ''
    toast.success(`Rol asignado: ${label}.`)
    emit('assigned', detail)
  } catch (err) {
    error.value = userErrorMessage(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="space-y-2" data-testid="role-assigner">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-end">
      <label class="block flex-1 text-sm font-medium text-text-muted">
        Asignar un rol
        <UiSelect
          v-model="roleId"
          class="mt-1"
          :options="options"
          :disabled="saving || options.length === 0"
          :placeholder="options.length ? 'Aplicación → Rol' : 'No hay más roles activos para asignar'"
          data-testid="role-select"
        />
      </label>
      <UiButton :disabled="!roleId" :loading="saving" data-testid="role-assign" @click="assign">Asignar rol</UiButton>
    </div>
    <UiAlert v-if="error" :message="error" data-testid="assign-error" />
  </div>
</template>
