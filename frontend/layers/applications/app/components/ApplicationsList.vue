<script setup lang="ts">
import type { UiDataTableColumn } from '#andromeda/components/ui/UiDataTable.vue'
import type { ApplicationRead } from '../types/applications'
import { isProtectedApp } from '../utils/actionTag'

/**
 * Listado de aplicaciones: búsqueda, filtro activas/inactivas, paginación y
 * acciones por fila (ver, editar, activar/desactivar, rotar secreto), cada una
 * bajo su tag `leo.applications.*`. La app `leo` es protegida: solo se ve.
 */
const list = useApplicationsList()
const actions = useApplicationsAppActions(() => list.load())

const formOpen = ref(false)
const editing = ref<ApplicationRead | null>(null)

function openCreate() {
  editing.value = null
  formOpen.value = true
}

function openEdit(app: ApplicationRead) {
  editing.value = app
  formOpen.value = true
}

function onCreated(created: Parameters<typeof actions.revealCreated>[0]) {
  actions.revealCreated(created)
  void list.load()
}

onMounted(() => list.load())

const columns: UiDataTableColumn<ApplicationRead>[] = [
  { key: 'name', label: 'Aplicación' },
  { key: 'base_url', label: 'URL base' },
  { key: 'is_active', label: 'Estado' },
  { key: 'id', label: 'Acciones', class: 'text-right' }
]
</script>

<template>
  <div class="space-y-4">
    <UiPageHeader title="Aplicaciones" description="Apps del ecosistema registradas en Leo, con sus módulos y acciones.">
      <template #actions>
        <LeoCan tag="leo.applications.create">
          <UiButton data-testid="app-create" @click="openCreate">Nueva aplicación</UiButton>
        </LeoCan>
      </template>
    </UiPageHeader>

    <UiListToolbar v-model:search="list.search.value" search-placeholder="Buscar por nombre o identificador…" :searching="list.loading.value">
      <UiActiveFilter v-model="list.active.value" all-label="Todas" active-label="Activas" inactive-label="Inactivas" />
    </UiListToolbar>

    <UiAlert v-if="list.error.value" :message="list.error.value" data-testid="apps-error" />

    <UiDataTable
      v-model:page="list.page.value"
      :columns="columns"
      :rows="list.items.value"
      :loading="list.loading.value"
      :page-size="list.pageSize"
      :total="list.total.value"
      :search-term="list.search.value"
      empty-message="Aún no hay aplicaciones registradas."
      @clear-search="list.search.value = ''"
    >
      <template #cell-name="{ row }">
        <div class="font-medium text-text">{{ row.name }}</div>
        <div class="text-xs text-text-muted"><code>{{ row.slug }}</code></div>
      </template>
      <template #cell-is_active="{ row }">
        <UiStatusBadge :active="row.is_active" />
      </template>
      <template #cell-id="{ row }">
        <div class="flex flex-wrap items-center justify-end gap-1">
          <UiButton :to="`/applications/${row.id}`" variant="ghost" size="sm">Ver</UiButton>
          <template v-if="!isProtectedApp(row.slug)">
            <LeoCan tag="leo.applications.edit">
              <UiButton variant="ghost" size="sm" data-testid="app-edit" @click="openEdit(row)">Editar</UiButton>
            </LeoCan>
            <LeoCan tag="leo.applications.rotate-secret">
              <UiButton variant="ghost" size="sm" data-testid="app-rotate" @click="actions.rotate.ask(row)">Rotar secreto</UiButton>
            </LeoCan>
            <LeoCan tag="leo.applications.deactivate">
              <UiButton :variant="row.is_active ? 'danger-ghost' : 'ghost'" size="sm" data-testid="app-toggle" @click="actions.toggle.ask(row)">
                {{ row.is_active ? 'Desactivar' : 'Activar' }}
              </UiButton>
            </LeoCan>
          </template>
        </div>
      </template>
    </UiDataTable>

    <LeoCan :tag="['leo.applications.create', 'leo.applications.edit']" any>
      <ApplicationsFormModal v-model:open="formOpen" :application="editing" @created="onCreated" @updated="list.load()" />
    </LeoCan>
    <ApplicationsAppDialogs :actions="actions" />
  </div>
</template>
