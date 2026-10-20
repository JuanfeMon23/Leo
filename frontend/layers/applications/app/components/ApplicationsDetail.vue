<script setup lang="ts">
import type {
  ApplicationActionRead,
  ApplicationDetail,
  ApplicationModuleRead,
  ApplicationModuleWithActions,
  ApplicationRead
} from '../types/applications'
import { isProtectedApp } from '../utils/actionTag'
import { applicationErrorMessage } from '../utils/applicationErrors'

/**
 * Detalle de una aplicación: datos, módulos y acciones. Las acciones de
 * eventos (descripción "Evento: …") las registra la semilla: llevan la
 * insignia «Evento» y no tienen controles. La app `leo` es protegida: toda la
 * pantalla queda en solo lectura. Cada control va bajo su tag `leo.applications.*`.
 */
const props = defineProps<{ id: string }>()

const api = useApplicationsApi()
const toast = useToast()

const detail = ref<ApplicationDetail | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    detail.value = await api.get(props.id)
  } catch (err) {
    error.value = applicationErrorMessage(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(() => props.id, load)

const readonly = computed(() => (detail.value ? isProtectedApp(detail.value.slug) : false))

// --- aplicación (editar, desactivar, rotar secreto) ---
const appActions = useApplicationsAppActions(load)
const appFormOpen = ref(false)

// --- módulos ---
const moduleFormOpen = ref(false)
const editingModule = ref<ApplicationModuleRead | null>(null)

function openNewModule() {
  editingModule.value = null
  moduleFormOpen.value = true
}

function openEditModule(module: ApplicationModuleRead) {
  editingModule.value = module
  moduleFormOpen.value = true
}

const moduleToggle = useApplicationsConfirm(async (module: ApplicationModuleWithActions) => {
  const next = !module.is_active
  await api.setModuleActive(props.id, module.id, next)
  toast.success(next ? `Módulo «${module.name}» activado.` : `Módulo «${module.name}» desactivado.`)
  await load()
})

// --- acciones ---
const actionFormOpen = ref(false)
const actionModule = ref<ApplicationModuleWithActions | null>(null)
const editingAction = ref<ApplicationActionRead | null>(null)

function openNewAction(module: ApplicationModuleWithActions) {
  actionModule.value = module
  editingAction.value = null
  actionFormOpen.value = true
}

function openEditAction(module: ApplicationModuleWithActions, action: ApplicationActionRead) {
  actionModule.value = module
  editingAction.value = action
  actionFormOpen.value = true
}

const actionToggle = useApplicationsConfirm(async (action: ApplicationActionRead) => {
  const next = !action.is_active
  await api.setActionActive(props.id, action.id, next)
  toast.success(next ? `Acción «${action.name}» activada.` : `Acción «${action.name}» desactivada.`)
  await load()
})

const asApplication = computed<ApplicationRead | null>(() => detail.value)
</script>

<template>
  <div class="space-y-6">
    <div>
      <NuxtLink to="/applications" class="text-sm text-primary-700 hover:underline">← Aplicaciones</NuxtLink>
    </div>

    <UiAlert v-if="error" :message="error" data-testid="detail-error" />
    <div v-else-if="loading && !detail" class="flex items-center gap-2 text-text-muted"><UiSpinner size="md" color="primary" /> Cargando…</div>

    <template v-if="detail">
      <UiPageHeader :title="detail.name" :description="detail.description ?? undefined">
        <template #actions>
          <UiStatusBadge :active="detail.is_active" />
          <template v-if="!readonly">
            <LeoCan tag="leo.applications.edit">
              <UiButton variant="secondary" data-testid="app-edit" @click="appFormOpen = true">Editar</UiButton>
            </LeoCan>
            <LeoCan tag="leo.applications.rotate-secret">
              <UiButton variant="secondary" data-testid="app-rotate" @click="appActions.rotate.ask(detail)">Rotar secreto</UiButton>
            </LeoCan>
            <LeoCan tag="leo.applications.deactivate">
              <UiButton :variant="detail.is_active ? 'danger' : 'primary'" data-testid="app-toggle" @click="appActions.toggle.ask(detail)">
                {{ detail.is_active ? 'Desactivar' : 'Activar' }}
              </UiButton>
            </LeoCan>
          </template>
        </template>
      </UiPageHeader>

      <UiAlert v-if="readonly" variant="info" title="Aplicación protegida" data-testid="readonly-notice">
        Leo es la app que administra el acceso de todas las demás: la mantiene el sistema y aquí solo se puede consultar.
      </UiAlert>

      <UiCard title="Datos de la aplicación">
        <dl class="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt class="font-medium text-text-muted">Identificador (client_id)</dt>
            <dd class="mt-1"><code>{{ detail.client_id }}</code></dd>
          </div>
          <div>
            <dt class="font-medium text-text-muted">URL base</dt>
            <dd class="mt-1 break-all">{{ detail.base_url }}</dd>
          </div>
          <div class="sm:col-span-2">
            <dt class="font-medium text-text-muted">Redirect URIs</dt>
            <dd class="mt-1">
              <ul v-if="detail.redirect_uris.length" class="space-y-1">
                <li v-for="uri in detail.redirect_uris" :key="uri" class="break-all"><code>{{ uri }}</code></li>
              </ul>
              <span v-else class="text-text-muted">Sin redirect URIs.</span>
            </dd>
          </div>
        </dl>
      </UiCard>

      <section class="space-y-4" aria-labelledby="modules-title">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 id="modules-title" class="text-lg font-semibold text-text">Módulos y acciones</h3>
          <LeoCan v-if="!readonly" tag="leo.applications.create">
            <UiButton variant="secondary" data-testid="module-create" @click="openNewModule">Nuevo módulo</UiButton>
          </LeoCan>
        </div>

        <UiCard v-if="detail.modules.length === 0">
          <p class="text-sm text-text-muted">Esta aplicación aún no tiene módulos.</p>
        </UiCard>

        <UiCard v-for="module in detail.modules" :key="module.id" :title="module.name" :description="module.description ?? undefined" data-testid="module-card">
          <template #actions>
            <code class="text-xs text-text-muted">{{ module.slug }}</code>
            <UiStatusBadge :active="module.is_active" />
            <template v-if="!readonly">
              <LeoCan tag="leo.applications.edit">
                <UiButton variant="ghost" size="sm" data-testid="module-edit" @click="openEditModule(module)">Editar</UiButton>
              </LeoCan>
              <LeoCan tag="leo.applications.deactivate">
                <UiButton :variant="module.is_active ? 'danger-ghost' : 'ghost'" size="sm" data-testid="module-toggle" @click="moduleToggle.ask(module)">
                  {{ module.is_active ? 'Desactivar' : 'Activar' }}
                </UiButton>
              </LeoCan>
            </template>
          </template>

          <ul v-if="module.actions.length" class="divide-y divide-border">
            <li v-for="action in module.actions" :key="action.id" class="flex flex-wrap items-center justify-between gap-2 py-2" data-testid="action-row">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-sm font-medium text-text" data-testid="action-name">{{ action.name }}</span>
                  <UiStatusBadge v-if="isEventAction(action.description)" variant="primary" label="Evento" data-testid="event-badge" />
                  <UiStatusBadge :active="action.is_active" />
                </div>
                <code class="break-all text-xs text-text-muted" data-testid="action-tag">{{ action.tag }}</code>
                <p v-if="action.description" class="mt-0.5 text-sm text-text-muted">{{ action.description }}</p>
              </div>
              <div v-if="!readonly && !isEventAction(action.description)" class="flex items-center gap-1">
                <LeoCan tag="leo.applications.edit">
                  <UiButton variant="ghost" size="sm" data-testid="action-edit" @click="openEditAction(module, action)">Editar</UiButton>
                </LeoCan>
                <LeoCan tag="leo.applications.deactivate">
                  <UiButton :variant="action.is_active ? 'danger-ghost' : 'ghost'" size="sm" data-testid="action-toggle" @click="actionToggle.ask(action)">
                    {{ action.is_active ? 'Desactivar' : 'Activar' }}
                  </UiButton>
                </LeoCan>
              </div>
            </li>
          </ul>
          <p v-else class="text-sm text-text-muted">Este módulo aún no tiene acciones.</p>

          <div v-if="!readonly" class="mt-3">
            <LeoCan tag="leo.applications.create">
              <UiButton variant="secondary" size="sm" data-testid="action-create" @click="openNewAction(module)">Nueva acción</UiButton>
            </LeoCan>
          </div>
        </UiCard>
      </section>

      <LeoCan v-if="!readonly" :tag="['leo.applications.edit']">
        <ApplicationsFormModal v-model:open="appFormOpen" :application="asApplication" @updated="load" />
      </LeoCan>
      <LeoCan v-if="!readonly" :tag="['leo.applications.create', 'leo.applications.edit']" any>
        <ApplicationsModuleFormModal v-model:open="moduleFormOpen" :app-id="detail.id" :module="editingModule" @saved="load" />
        <ApplicationsActionFormModal
          v-if="actionModule"
          v-model:open="actionFormOpen"
          :app-id="detail.id"
          :app-slug="detail.slug"
          :module-id="actionModule.id"
          :module-slug="actionModule.slug"
          :action="editingAction"
          @saved="load"
        />
      </LeoCan>

      <UiConfirmModal
        v-model:open="moduleToggle.open"
        :title="moduleToggle.target?.is_active ? 'Desactivar módulo' : 'Activar módulo'"
        :message="`${moduleToggle.target?.is_active ? 'Se desactivará' : 'Se activará'} el módulo «${moduleToggle.target?.name}».`"
        :confirm-label="moduleToggle.target?.is_active ? 'Desactivar' : 'Activar'"
        :variant="moduleToggle.target?.is_active ? 'danger' : 'primary'"
        :loading="moduleToggle.loading"
        :error="moduleToggle.error"
        @confirm="moduleToggle.confirm()"
      />
      <UiConfirmModal
        v-model:open="actionToggle.open"
        :title="actionToggle.target?.is_active ? 'Desactivar acción' : 'Activar acción'"
        :message="`${actionToggle.target?.is_active ? 'Se desactivará' : 'Se activará'} la acción «${actionToggle.target?.name}» (${actionToggle.target?.tag}).`"
        :confirm-label="actionToggle.target?.is_active ? 'Desactivar' : 'Activar'"
        :variant="actionToggle.target?.is_active ? 'danger' : 'primary'"
        :loading="actionToggle.loading"
        :error="actionToggle.error"
        @confirm="actionToggle.confirm()"
      />
    </template>

    <ApplicationsAppDialogs :actions="appActions" />
  </div>
</template>
