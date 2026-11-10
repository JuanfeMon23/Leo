<script setup lang="ts">
import type { UiDataTableColumn } from '#andromeda/components/ui/UiDataTable.vue'
import type { DocumentTypeRead, DocumentTypeRow } from '../types/documentTypes'

/**
 * Gestión del catálogo de tipos de documento: activos e inactivos, crear,
 * editar nombre y orden, activar/desactivar; cada acción bajo su tag
 * `leo.document-types.*`.
 */
const admin = useDocumentTypesAdmin()

const formOpen = ref(false)
const editing = ref<DocumentTypeRead | null>(null)

function openCreate() {
  editing.value = null
  formOpen.value = true
}

function openEdit(type: DocumentTypeRead) {
  editing.value = type
  formOpen.value = true
}

onMounted(() => { void admin.load() })

const columns: UiDataTableColumn<DocumentTypeRow>[] = [
  { key: 'code', label: 'Código' },
  { key: 'name', label: 'Nombre' },
  { key: 'sort_order', label: 'Orden' },
  { key: 'is_active', label: 'Estado' },
  { key: 'actions', label: 'Acciones', class: 'text-right' }
]

const deactivating = computed(() => admin.toggle.target?.is_active ?? true)
</script>

<template>
  <div class="space-y-4">
    <UiPageHeader title="Tipos de documento" description="Catálogo de tipos de documento que se ofrecen al registrar usuarios.">
      <template #actions>
        <LeoCan tag="leo.document-types.create">
          <UiButton data-testid="document-type-create" @click="openCreate">Nuevo tipo</UiButton>
        </LeoCan>
      </template>
    </UiPageHeader>

    <UiListToolbar v-model:search="admin.search.value" search-placeholder="Buscar por código o nombre…" :searching="admin.loading.value">
      <UiActiveFilter v-model="admin.active.value" all-label="Todos" active-label="Activos" inactive-label="Inactivos" />
    </UiListToolbar>

    <UiAlert v-if="admin.error.value" :message="admin.error.value" data-testid="document-types-error" />

    <UiDataTable
      :columns="columns"
      :rows="admin.rows.value"
      :loading="admin.loading.value"
      :row-key="row => row.code"
      :search-term="admin.search.value"
      empty-message="Aún no hay tipos de documento registrados."
      @clear-search="admin.search.value = ''"
    >
      <template #cell-code="{ row }">
        <code>{{ row.code }}</code>
      </template>
      <template #cell-is_active="{ row }">
        <UiStatusBadge :active="row.is_active" />
      </template>
      <template #cell-actions="{ row }">
        <div class="flex flex-wrap items-center justify-end gap-1">
          <LeoCan tag="leo.document-types.edit">
            <UiButton variant="ghost" size="sm" data-testid="document-type-edit" @click="openEdit(row)">Editar</UiButton>
          </LeoCan>
          <LeoCan tag="leo.document-types.deactivate">
            <UiButton :variant="row.is_active ? 'danger-ghost' : 'ghost'" size="sm" data-testid="document-type-toggle" @click="admin.toggle.ask(row)">
              {{ row.is_active ? 'Desactivar' : 'Activar' }}
            </UiButton>
          </LeoCan>
        </div>
      </template>
    </UiDataTable>

    <LeoCan :tag="['leo.document-types.create', 'leo.document-types.edit']" any>
      <DocumentTypesFormModal v-model:open="formOpen" :type="editing" @saved="admin.load()" />
    </LeoCan>
    <UiConfirmModal
      v-model:open="admin.toggle.open"
      :title="deactivating ? 'Desactivar tipo de documento' : 'Activar tipo de documento'"
      :message="deactivating
        ? `Se desactivará «${admin.toggle.target?.name}»: dejará de ofrecerse al registrar usuarios; los ya registrados lo conservan. Podrás reactivarlo cuando quieras.`
        : `Se activará «${admin.toggle.target?.name}».`"
      :confirm-label="deactivating ? 'Desactivar' : 'Activar'"
      :variant="deactivating ? 'danger' : 'primary'"
      :loading="admin.toggle.loading"
      :error="admin.toggle.error"
      @confirm="admin.toggle.confirm()"
    />
  </div>
</template>
