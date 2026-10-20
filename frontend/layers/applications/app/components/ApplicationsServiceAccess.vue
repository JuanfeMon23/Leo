<script setup lang="ts">
import type { ApplicationsServiceGrant } from '../types/applications'
import { applicationsGroupServiceGrants, applicationsServiceAccessErrorMessage } from '../utils/serviceAccess'

/**
 * «Acceso a otras aplicaciones» de una app: a qué aplicaciones puede
 * consultar con su credencial de servicio y con qué roles (agrupado por
 * destino). Solo se monta con `leo.applications.grant-service-access`
 * (el padre lo envuelve en `LeoCan`), así que no consulta nada sin el permiso.
 */
const props = defineProps<{ appId: string, appName: string }>()

const api = useApplicationsApi()
const toast = useToast()

const grants = ref<ApplicationsServiceGrant[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const grantOpen = ref(false)

const groups = computed(() => applicationsGroupServiceGrants(grants.value))

async function load() {
  loading.value = true
  error.value = null
  try {
    grants.value = await api.listServiceAccess(props.appId)
  } catch (err) {
    error.value = applicationsServiceAccessErrorMessage(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(() => props.appId, load)

const revoke = useConfirmAction(async (grant: ApplicationsServiceGrant) => {
  try {
    await api.revokeServiceAccess(props.appId, grant.role.id)
  } catch (err) {
    throw new Error(applicationsServiceAccessErrorMessage(err))
  }
  toast.success(`${props.appName} ya no puede consultar ${grant.application.name} con el rol «${grant.role.name}».`)
  await load()
})
</script>

<template>
  <section class="space-y-4" aria-labelledby="service-access-title" data-testid="service-access">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h3 id="service-access-title" class="text-lg font-semibold text-text">Acceso a otras aplicaciones</h3>
        <p class="text-sm text-text-muted">Aplicaciones que {{ appName }} puede consultar por su cuenta, solo con los permisos de los roles concedidos.</p>
      </div>
      <UiButton variant="secondary" data-testid="grant-open" @click="grantOpen = true">Conceder acceso</UiButton>
    </div>

    <UiAlert variant="info" data-testid="service-ttl-notice">Los tokens de servicio duran minutos y no se atan a un dispositivo.</UiAlert>

    <UiAlert v-if="error" :message="error" data-testid="service-error" />
    <div v-else-if="loading && grants.length === 0" class="flex items-center gap-2 text-text-muted"><UiSpinner size="md" color="primary" /> Cargando…</div>
    <UiCard v-else-if="groups.length === 0">
      <p class="text-sm text-text-muted" data-testid="service-empty">{{ appName }} no tiene acceso concedido a otras aplicaciones.</p>
    </UiCard>

    <UiCard v-for="group in groups" :key="group.application.id" :title="group.application.name" data-testid="service-group">
      <template #actions>
        <code class="text-xs text-text-muted">{{ group.application.slug }}</code>
      </template>
      <ul class="divide-y divide-border">
        <li v-for="grant in group.grants" :key="grant.id" class="flex flex-wrap items-start justify-between gap-3 py-3" data-testid="service-grant">
          <div class="min-w-0 space-y-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-sm font-medium text-text" data-testid="grant-role-name">Rol: {{ grant.role.name }}</span>
              <UiStatusBadge v-if="!grant.role.is_active" :active="false" data-testid="grant-role-inactive" />
            </div>
            <ApplicationsPermissionList :permissions="grant.permissions" />
          </div>
          <UiButton variant="danger-ghost" size="sm" data-testid="grant-revoke" @click="revoke.ask(grant)">Quitar acceso</UiButton>
        </li>
      </ul>
    </UiCard>

    <ApplicationsServiceGrantModal v-model:open="grantOpen" :app-id="appId" :app-name="appName" @granted="load" />

    <UiConfirmModal
      v-model:open="revoke.open"
      title="Quitar acceso"
      :message="`${appName} dejará de poder consultar ${revoke.target?.application.name} con el rol «${revoke.target?.role.name}». Sus tokens de servicio con este rol se revocan de inmediato.`"
      confirm-label="Quitar acceso"
      :loading="revoke.loading"
      :error="revoke.error"
      @confirm="revoke.confirm()"
    />
  </section>
</template>
