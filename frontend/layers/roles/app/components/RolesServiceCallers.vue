<script setup lang="ts">
import type { RolesServiceCaller } from '../types/roles'
import { roleErrorMessage } from '../utils/roleErrors'

/**
 * «Aplicaciones con acceso de servicio a este rol»: solo lectura. Qué apps
 * pueden consultar la aplicación del rol, por su cuenta, con estos permisos.
 * Se concede desde el detalle de cada aplicación. El padre la envuelve en
 * `LeoCan` (`leo.applications.grant-service-access`): sin él no consulta nada.
 */
const props = defineProps<{ roleId: string }>()

const api = useRolesApi()

const callers = ref<RolesServiceCaller[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    callers.value = await api.listServiceCallers(props.roleId)
  } catch (err) {
    error.value = roleErrorMessage(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(() => props.roleId, load)
</script>

<template>
  <section class="space-y-3" aria-labelledby="service-callers-title" data-testid="service-callers">
    <div>
      <h3 id="service-callers-title" class="text-lg font-semibold text-text">Aplicaciones con acceso de servicio a este rol</h3>
      <p class="text-sm text-text-muted">Estas aplicaciones pueden consultar por su cuenta con los permisos de este rol. Se concede desde el detalle de cada aplicación.</p>
    </div>

    <UiAlert v-if="error" :message="error" data-testid="callers-error" />
    <div v-else-if="loading && callers.length === 0" class="flex items-center gap-2 text-text-muted"><UiSpinner size="md" color="primary" /> Cargando…</div>
    <UiCard v-else-if="callers.length === 0">
      <p class="text-sm text-text-muted" data-testid="callers-empty">Ninguna aplicación tiene acceso de servicio a este rol.</p>
    </UiCard>
    <UiCard v-else>
      <ul class="divide-y divide-border">
        <li v-for="caller in callers" :key="caller.id" class="flex flex-wrap items-center justify-between gap-2 py-2" data-testid="caller-row">
          <div class="flex flex-wrap items-center gap-2">
            <NuxtLink :to="`/applications/${caller.application.id}`" class="text-sm font-medium text-primary-700 hover:underline" data-testid="caller-link">
              {{ caller.application.name }}
            </NuxtLink>
            <UiStatusBadge v-if="!caller.application.is_active" :active="false" />
          </div>
          <code class="text-xs text-text-muted">{{ caller.application.slug }}</code>
        </li>
      </ul>
    </UiCard>
  </section>
</template>
