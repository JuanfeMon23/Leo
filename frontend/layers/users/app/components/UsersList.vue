<script setup lang="ts">
import type { UiDataTableColumn } from '#andromeda/components/ui/UiDataTable.vue'
import type { UserRead } from '../types/users'
import { usersDocument, usersFormatDateTime, usersFullName } from '../utils/userDisplay'

/**
 * Listado de usuarios: búsqueda (nombre, usuario, correo, documento),
 * activos/inactivos, paginación y acciones por fila (ver, editar), cada una
 * bajo su tag `leo.users.*`.
 */
const list = useUsersList()

const createOpen = ref(false)
const editOpen = ref(false)
const editing = ref<UserRead | null>(null)

function openEdit(user: UserRead) {
  editing.value = user
  editOpen.value = true
}

onMounted(() => void list.load())

const columns: UiDataTableColumn<UserRead>[] = [
  { key: 'first_name', label: 'Nombre' },
  { key: 'username', label: 'Usuario' },
  { key: 'email', label: 'Correo' },
  { key: 'document_number', label: 'Documento' },
  { key: 'is_active', label: 'Estado' },
  { key: 'last_login_at', label: 'Último acceso' },
  { key: 'id', label: 'Acciones', class: 'text-right' }
]
</script>

<template>
  <div class="space-y-4">
    <UiPageHeader title="Usuarios" description="Las personas que acceden a las aplicaciones del ecosistema y los roles que tienen en cada una.">
      <template #actions>
        <LeoCan tag="leo.users.create">
          <UiButton data-testid="user-create" @click="createOpen = true">Nuevo usuario</UiButton>
        </LeoCan>
      </template>
    </UiPageHeader>

    <UiListToolbar v-model:search="list.search.value" search-placeholder="Buscar por nombre, usuario, correo o documento…" :searching="list.loading.value">
      <UiActiveFilter v-model="list.active.value" all-label="Todos" active-label="Activos" inactive-label="Inactivos" />
    </UiListToolbar>

    <UiAlert v-if="list.error.value" :message="list.error.value" data-testid="users-error" />

    <UiDataTable
      v-model:page="list.page.value"
      :columns="columns"
      :rows="list.items.value"
      :loading="list.loading.value"
      :page-size="list.pageSize"
      :total="list.total.value"
      :search-term="list.search.value"
      empty-message="Aún no hay usuarios registrados."
      @clear-search="list.search.value = ''"
    >
      <template #cell-first_name="{ row }">
        <div class="font-medium text-text" data-testid="user-name">{{ usersFullName(row) }}</div>
      </template>
      <template #cell-username="{ row }">
        <code>{{ row.username }}</code>
      </template>
      <template #cell-document_number="{ row }">
        {{ usersDocument(row) }}
      </template>
      <template #cell-is_active="{ row }">
        <UsersStatusBadge :user="row" />
      </template>
      <template #cell-last_login_at="{ row }">
        <span class="text-text-muted">{{ usersFormatDateTime(row.last_login_at) }}</span>
      </template>
      <template #cell-id="{ row }">
        <div class="flex flex-wrap items-center justify-end gap-1">
          <UiButton :to="`/users/${row.id}`" variant="ghost" size="sm" data-testid="user-view">Ver</UiButton>
          <LeoCan tag="leo.users.edit">
            <UiButton variant="ghost" size="sm" data-testid="user-edit" @click="openEdit(row)">Editar</UiButton>
          </LeoCan>
        </div>
      </template>
    </UiDataTable>

    <LeoCan tag="leo.users.create">
      <UsersCreateModal v-model:open="createOpen" @saved="list.load()" />
    </LeoCan>
    <LeoCan tag="leo.users.edit">
      <UsersEditModal v-model:open="editOpen" :user="editing" @saved="list.load()" />
    </LeoCan>
  </div>
</template>
