<script setup lang="ts">
import type { UiDataTableColumn } from '#andromeda/components/ui/UiDataTable.vue'
import type { RoleRead } from '../types/roles'

/**
 * Listado de roles: filtro por aplicación, búsqueda, activos/inactivos,
 * paginación y acciones por fila (ver permisos, editar, activar/desactivar),
 * cada una bajo su tag `leo.roles.*`.
 */
const list = useRolesList()
const toggle = useRolesToggle(() => list.load())

const formOpen = ref(false)
const editing = ref<RoleRead | null>(null)

function openCreate() {
  editing.value = null
  formOpen.value = true
}

function openEdit(role: RoleRead) {
  editing.value = role
  formOpen.value = true
}

onMounted(() => {
  void list.load()
  void list.loadApplications()
})

const appFilterOptions = computed(() => list.applications.value.map(a => ({ value: a.id, label: a.name })))

const columns: UiDataTableColumn<RoleRead>[] = [
  { key: 'name', label: 'Rol' },
  { key: 'application_id', label: 'Aplicación' },
  { key: 'is_active', label: 'Estado' },
  { key: 'id', label: 'Acciones', class: 'text-right' }
]
</script>

<template>
  <div class="space-y-4">
    <UiPageHeader title="Roles" description="Agrupan los permisos que se asignan a los usuarios, por aplicación.">
      <template #actions>
        <LeoCan tag="leo.roles.create">
          <UiButton data-testid="role-create" @click="openCreate">Nuevo rol</UiButton>
        </LeoCan>
      </template>
    </UiPageHeader>

    <UiListToolbar v-model:search="list.search.value" search-placeholder="Buscar por nombre o identificador…" :searching="list.loading.value">
      <UiSelect
        v-model="list.applicationId.value"
        class="w-full sm:w-56"
        aria-label="Filtrar por aplicación"
        empty-label="Todas las aplicaciones"
        :options="appFilterOptions"
        data-testid="app-filter"
      />
      <UiActiveFilter v-model="list.active.value" all-label="Todos" active-label="Activos" inactive-label="Inactivos" />
    </UiListToolbar>

    <UiAlert v-if="list.error.value" :message="list.error.value" data-testid="roles-error" />
    <UiAlert v-if="list.applicationsError.value" variant="warning" :message="`No se pudo cargar la lista de aplicaciones: ${list.applicationsError.value}`" data-testid="apps-error" />

    <UiDataTable
      v-model:page="list.page.value"
      :columns="columns"
      :rows="list.items.value"
      :loading="list.loading.value"
      :page-size="list.pageSize"
      :total="list.total.value"
      :search-term="list.search.value"
      empty-message="Aún no hay roles registrados."
      @clear-search="list.search.value = ''"
    >
      <template #cell-name="{ row }">
        <div class="font-medium text-text">{{ row.name }}</div>
        <div class="text-xs text-text-muted"><code>{{ row.slug }}</code></div>
      </template>
      <template #cell-application_id="{ row }">
        {{ list.applicationName(row.application_id) }}
      </template>
      <template #cell-is_active="{ row }">
        <UiStatusBadge :active="row.is_active" />
      </template>
      <template #cell-id="{ row }">
        <div class="flex flex-wrap items-center justify-end gap-1">
          <UiButton :to="`/roles/${row.id}`" variant="ghost" size="sm" data-testid="role-view">Permisos</UiButton>
          <LeoCan tag="leo.roles.edit">
            <UiButton variant="ghost" size="sm" data-testid="role-edit" @click="openEdit(row)">Editar</UiButton>
          </LeoCan>
          <LeoCan tag="leo.roles.deactivate">
            <UiButton :variant="row.is_active ? 'danger-ghost' : 'ghost'" size="sm" data-testid="role-toggle" @click="toggle.ask(row)">
              {{ row.is_active ? 'Desactivar' : 'Activar' }}
            </UiButton>
          </LeoCan>
        </div>
      </template>
    </UiDataTable>

    <LeoCan :tag="['leo.roles.create', 'leo.roles.edit']" any>
      <RolesFormModal
        v-model:open="formOpen"
        :role="editing"
        :applications="list.applications.value"
        :default-application-id="list.applicationId.value"
        @saved="list.load()"
      />
    </LeoCan>
    <RolesToggleConfirm :toggle="toggle" />
  </div>
</template>
