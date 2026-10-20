<script setup lang="ts">
import type { ApplicationRead, ApplicationsGrantableRole } from '../types/applications'
import { applicationsGrantSummary, applicationsGrantableTargets, applicationsServiceAccessErrorMessage } from '../utils/serviceAccess'

/**
 * Conceder acceso a otra aplicación: se elige la aplicación destino (no la
 * actual ni Leo) y, de sus roles ACTIVOS, los que la app llamadora podrá usar
 * con su credencial de servicio. Cada rol muestra sus permisos legibles para
 * decidir. Todo o nada: un solo POST con los roles marcados.
 */
const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ appId: string, appName: string }>()
const emit = defineEmits<{ granted: [] }>()

const api = useApplicationsApi()
const toast = useToast()

const targets = ref<ApplicationRead[]>([])
const targetId = ref('')
const roles = ref<ApplicationsGrantableRole[]>([])
const selected = ref<Set<string>>(new Set())
const loadingTargets = ref(false)
const loadingRoles = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)

const targetOptions = computed(() => targets.value.map(a => ({ value: a.id, label: a.name })))
const targetName = computed(() => targets.value.find(a => a.id === targetId.value)?.name ?? '')

async function loadTargets() {
  loadingTargets.value = true
  try {
    targets.value = applicationsGrantableTargets((await api.listAllApplications()).items, props.appId)
  } catch (err) {
    error.value = applicationsServiceAccessErrorMessage(err)
  } finally {
    loadingTargets.value = false
  }
}

async function loadRoles(applicationId: string) {
  loadingRoles.value = true
  roles.value = []
  selected.value = new Set()
  error.value = null
  try {
    const page = await api.listActiveRoles(applicationId)
    const withPermissions = await Promise.all(page.items.filter(r => r.is_active).map(async (role): Promise<ApplicationsGrantableRole> => {
      try {
        return { id: role.id, slug: role.slug, name: role.name, description: role.description, permissions: await api.getRolePermissions(role.id) }
      } catch {
        return { id: role.id, slug: role.slug, name: role.name, description: role.description, permissions: null }
      }
    }))
    // Una respuesta tardía de otra aplicación ya no es la elegida: se descarta.
    if (applicationId === targetId.value) roles.value = withPermissions
  } catch (err) {
    if (applicationId === targetId.value) error.value = applicationsServiceAccessErrorMessage(err)
  } finally {
    if (applicationId === targetId.value) loadingRoles.value = false
  }
}

watch(targetId, (id) => {
  if (id) void loadRoles(id)
  else {
    roles.value = []
    selected.value = new Set()
  }
})

watch(open, (isOpen) => {
  if (!isOpen) return
  targetId.value = ''
  roles.value = []
  selected.value = new Set()
  error.value = null
  void loadTargets()
})

function toggle(id: string, on: boolean) {
  const next = new Set(selected.value)
  if (on) next.add(id)
  else next.delete(id)
  selected.value = next
}

async function submit() {
  if (selected.value.size === 0) return
  submitting.value = true
  error.value = null
  try {
    await api.grantServiceAccess(props.appId, [...selected.value])
    toast.success(`${props.appName} ahora puede consultar ${targetName.value}.`)
    open.value = false
    emit('granted')
  } catch (err) {
    error.value = applicationsServiceAccessErrorMessage(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UiModal v-model:open="open" title="Conceder acceso a otra aplicación" :description="`Elige qué aplicación podrá consultar ${appName} y con qué roles.`" size="lg" :dismissable="!submitting">
    <div class="space-y-4">
      <UiAlert v-if="error" :message="error" data-testid="grant-error" />

      <div>
        <label for="grant-target" class="mb-1 block text-sm font-medium text-text">Aplicación a consultar</label>
        <UiSelect
          id="grant-target"
          v-model="targetId"
          placeholder="Elige una aplicación"
          :options="targetOptions"
          :disabled="loadingTargets || submitting"
          data-testid="grant-target"
        />
      </div>

      <div v-if="loadingRoles" class="flex items-center gap-2 text-sm text-text-muted"><UiSpinner size="sm" color="primary" /> Cargando roles…</div>

      <template v-else-if="targetId">
        <p v-if="roles.length === 0 && !error" class="text-sm text-text-muted" data-testid="grant-no-roles">
          {{ targetName }} no tiene roles activos que conceder.
        </p>
        <ul v-else class="divide-y divide-border rounded-lg border border-border" data-testid="grant-roles">
          <li v-for="role in roles" :key="role.id" class="space-y-2 px-4 py-3" data-testid="grant-role">
            <UiCheckbox
              :model-value="selected.has(role.id)"
              :description="role.description ?? undefined"
              :disabled="submitting"
              data-testid="grant-role-check"
              @update:model-value="toggle(role.id, $event)"
            >
              <span class="font-medium">{{ role.name }}</span>
            </UiCheckbox>
            <div class="pl-7">
              <ApplicationsPermissionList :permissions="role.permissions" />
            </div>
          </li>
        </ul>
      </template>

      <UiAlert v-if="selected.size > 0" variant="info" data-testid="grant-summary">
        {{ applicationsGrantSummary(appName, targetName) }}
      </UiAlert>
    </div>

    <template #footer>
      <UiButton variant="ghost" :disabled="submitting" data-testid="grant-cancel" @click="open = false">Cancelar</UiButton>
      <UiButton :disabled="selected.size === 0" :loading="submitting" data-testid="grant-submit" @click="submit">Conceder acceso</UiButton>
    </template>
  </UiModal>
</template>
