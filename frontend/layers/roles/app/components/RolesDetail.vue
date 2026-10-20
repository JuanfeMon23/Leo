<script setup lang="ts">
/**
 * Detalle de un rol: datos, activar/desactivar, editar y asignación de
 * permisos agrupados por módulo (los de la aplicación del rol). El editor
 * trabaja sobre un borrador: «Guardar cambios» aplica lo agregado y lo quitado.
 * Sin `leo.roles.edit` los permisos se ven en solo lectura.
 */
const props = defineProps<{ id: string }>()

const canEdit = useCan('leo.roles.edit')

const detail = useRolesDetail(() => props.id)
const { role, selected, model, diff, dirty, loading, error, catalogError, saving, saveError } = detail

onMounted(() => detail.load())
watch(() => props.id, () => detail.load())

const formOpen = ref(false)
const toggle = useRolesToggle(() => detail.refreshRole())

// El borrador de permisos se conserva al editar/activar el rol: solo se recargan sus datos.
const applicationName = computed(() => detail.catalog.value?.name ?? null)

// Solo para mostrar (bloqueada) la aplicación del rol en el formulario de edición.
const roleApplications = computed(() =>
  role.value ? [{ id: role.value.application_id, slug: detail.catalog.value?.slug ?? '', name: applicationName.value ?? '—', is_active: true }] : []
)

const changeSummary = computed(() => {
  const parts: string[] = []
  if (diff.value.add.length) parts.push(`${diff.value.add.length} por agregar`)
  if (diff.value.remove.length) parts.push(`${diff.value.remove.length} por quitar`)
  return parts.join(' · ')
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <NuxtLink to="/roles" class="text-sm text-primary-700 hover:underline">← Roles</NuxtLink>
    </div>

    <UiAlert v-if="error" :message="error" data-testid="detail-error" />
    <div v-else-if="loading && !role" class="flex items-center gap-2 text-text-muted"><UiSpinner size="md" color="primary" /> Cargando…</div>

    <template v-if="role">
      <UiPageHeader :title="role.name" :description="role.description ?? undefined">
        <template #actions>
          <UiStatusBadge :active="role.is_active" />
          <LeoCan tag="leo.roles.edit">
            <UiButton variant="secondary" data-testid="role-edit" @click="formOpen = true">Editar</UiButton>
          </LeoCan>
          <LeoCan tag="leo.roles.deactivate">
            <UiButton :variant="role.is_active ? 'danger' : 'primary'" data-testid="role-toggle" @click="toggle.ask(role)">
              {{ role.is_active ? 'Desactivar' : 'Activar' }}
            </UiButton>
          </LeoCan>
        </template>
      </UiPageHeader>

      <UiCard title="Datos del rol">
        <dl class="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt class="font-medium text-text-muted">Aplicación</dt>
            <dd class="mt-1" data-testid="role-app">{{ applicationName ?? '—' }}</dd>
          </div>
          <div>
            <dt class="font-medium text-text-muted">Identificador (slug)</dt>
            <dd class="mt-1"><code>{{ role.slug }}</code></dd>
          </div>
        </dl>
      </UiCard>

      <section class="space-y-4" aria-labelledby="permissions-title">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 id="permissions-title" class="text-lg font-semibold text-text">Permisos</h3>
            <p class="text-sm text-text-muted">Lo que podrán hacer los usuarios con este rol en {{ applicationName ?? 'la aplicación' }}.</p>
          </div>
        </div>

        <UiAlert v-if="catalogError" variant="warning" title="No se pudo cargar el catálogo de permisos" data-testid="catalog-error">
          {{ catalogError }} Se muestran solo los permisos ya asignados, en solo lectura.
        </UiAlert>
        <UiAlert v-if="saveError" :message="saveError" data-testid="save-error" />

        <RolesPermissionEditor v-model:selected="selected" :model="model" :readonly="!canEdit || Boolean(catalogError) || saving" />

        <LeoCan tag="leo.roles.edit">
          <div
            v-if="!catalogError"
            class="sticky bottom-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3 shadow-md"
            data-testid="save-bar"
          >
            <p class="text-sm" :class="dirty ? 'font-medium text-text' : 'text-text-muted'" data-testid="change-summary">
              {{ dirty ? `Cambios sin guardar: ${changeSummary}` : 'Sin cambios pendientes.' }}
            </p>
            <div class="flex items-center gap-2">
              <UiButton variant="ghost" :disabled="!dirty || saving" data-testid="discard" @click="detail.discard()">Descartar</UiButton>
              <UiButton :disabled="!dirty" :loading="saving" data-testid="save" @click="detail.save()">Guardar cambios</UiButton>
            </div>
          </div>
        </LeoCan>
      </section>

      <LeoCan tag="leo.roles.edit">
        <RolesFormModal v-model:open="formOpen" :role="role" :applications="roleApplications" @saved="detail.refreshRole()" />
      </LeoCan>
    </template>

    <RolesToggleConfirm :toggle="toggle" />
  </div>
</template>
