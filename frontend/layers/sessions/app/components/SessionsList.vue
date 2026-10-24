<script setup lang="ts">
import type { UiDataTableColumn } from '#andromeda/components/ui/UiDataTable.vue'
import type { SessionRead } from '../types/sessions'
import { sessionCanRevoke, sessionOwnerLabel, sessionStatus } from '../utils/sessionStatus'

/**
 * Sesiones SSO: las propias o las de un usuario elegido, solo activas o
 * todas. Cada fila dice de quién es, cuándo empezó, su última actividad,
 * cuándo expira, desde dónde (IP y navegador) y su estado; revocar exige
 * `leo.auth.revoke` y confirmación, y avisa si es la propia sesión.
 */
const list = useSessionsList()
const revoke = useSessionsRevoke(() => list.load())

onMounted(() => {
  void list.load()
  void list.loadUsers()
})

const userOptions = computed(() =>
  list.users.value.map(u => ({ value: u.id, label: `${`${u.first_name} ${u.last_name}`.trim()} (${u.username})` })))

const canRevoke = useCan('leo.auth.revoke')

// «Acciones» solo existe si hay algo que hacer: sin `leo.auth.revoke` la columna quedaría vacía.
const columns = computed<UiDataTableColumn<SessionRead>[]>(() => [
  { key: 'user_id', label: 'Usuario' },
  { key: 'created_at', label: 'Inicio' },
  { key: 'last_activity_at', label: 'Última actividad' },
  { key: 'expires_at', label: 'Expira' },
  { key: 'ip', label: 'Desde' },
  { key: 'revoked_at', label: 'Estado' },
  ...(canRevoke.value ? [{ key: 'id', label: 'Acciones', class: 'text-right' }] : [])
])
</script>

<template>
  <div class="space-y-4">
    <UiPageHeader title="Sesiones" description="Sesiones de inicio de sesión único: quién está conectado, desde dónde y hasta cuándo. Una sesión revocada deja de funcionar al instante." />

    <div class="flex flex-wrap items-end gap-x-4 gap-y-3">
      <UiFormField label="Sesiones de">
        <UiSelect
          v-model="list.userId.value"
          class="w-full sm:w-72"
          empty-label="Mis sesiones"
          :options="userOptions"
          data-testid="session-user-filter"
        />
      </UiFormField>
      <UiCheckbox v-model="list.activeOnly.value" label="Solo activas" data-testid="session-active-only" />
    </div>

    <UiAlert v-if="list.error.value" :message="list.error.value" data-testid="sessions-error" />
    <UiAlert
      v-if="list.usersError.value"
      variant="warning"
      :message="`No se pudo cargar la lista de usuarios: ${list.usersError.value} No podrás filtrar por usuario ni ver sus nombres.`"
      data-testid="sessions-users-error"
    />

    <UiDataTable
      v-model:page="list.page.value"
      :columns="columns"
      :rows="list.items.value"
      :loading="list.loading.value"
      :page-size="list.pageSize"
      :total="list.total.value"
      empty-message="No hay sesiones para mostrar."
    >
      <template #cell-user_id="{ row }">
        <div class="flex flex-wrap items-center gap-2">
          <div>
            <div class="font-medium text-text" data-testid="session-owner">{{ sessionOwnerLabel(row.user_id, list.users.value).name }}</div>
            <div v-if="sessionOwnerLabel(row.user_id, list.users.value).username" class="text-xs text-text-muted">
              {{ sessionOwnerLabel(row.user_id, list.users.value).username }}
            </div>
          </div>
          <UiStatusBadge v-if="row.is_current" variant="primary" label="Esta sesión" data-testid="session-current" />
        </div>
      </template>
      <template #cell-created_at="{ row }">
        <span class="whitespace-nowrap">{{ formatLocalDateTime(row.created_at) }}</span>
      </template>
      <template #cell-last_activity_at="{ row }">
        <span class="whitespace-nowrap">{{ formatLocalDateTime(row.last_activity_at) }}</span>
      </template>
      <template #cell-expires_at="{ row }">
        <span class="whitespace-nowrap">{{ formatLocalDateTime(row.expires_at) }}</span>
      </template>
      <template #cell-ip="{ row }">
        <div data-testid="session-ip">{{ row.ip || '—' }}</div>
        <div class="text-xs text-text-muted" :title="row.user_agent ?? undefined" data-testid="session-agent">{{ summarizeUserAgent(row.user_agent) }}</div>
      </template>
      <template #cell-revoked_at="{ row }">
        <SessionsStatusBadge :status="sessionStatus(row)" />
      </template>
      <template #cell-id="{ row }">
        <LeoCan tag="leo.auth.revoke">
          <UiButton
            v-if="sessionCanRevoke(row)"
            variant="danger-ghost"
            size="sm"
            data-testid="session-revoke"
            @click="revoke.ask(row)"
          >
            {{ row.is_current ? 'Cerrar esta sesión' : 'Revocar' }}
          </UiButton>
        </LeoCan>
      </template>
    </UiDataTable>

    <SessionsRevokeConfirm :revoke="revoke" />
  </div>
</template>
