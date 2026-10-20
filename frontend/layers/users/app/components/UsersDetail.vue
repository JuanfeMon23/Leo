<script setup lang="ts">
import type { UserRead, UserRoleRead } from '../types/users'
import { usersDocument, usersFormatDateTime, usersFullName, usersIsLocked } from '../utils/userDisplay'
import { USERS_DOCUMENT_LABELS } from '../utils/userSchemas'

/**
 * Detalle de un usuario: datos, estado, acceso por aplicación, roles
 * agrupados por aplicación (asignar/quitar) y permisos efectivos. Acciones
 * (cada una bajo su tag): editar, restablecer contraseña, desbloquear y
 * activar/desactivar. Nadie puede desactivarse a sí mismo: sobre el propio
 * usuario el botón no se ofrece (y si el backend responde 409, se explica).
 */
const props = defineProps<{ id: string }>()

const api = useUsersApi()
const toast = useToast()
const me = useLeoUser()

const detail = useUsersDetail(() => props.id)
const { user, groups, accessApps, roleOptions, effective, loading, error, lookupError } = detail

onMounted(() => detail.load())
watch(() => props.id, () => detail.load())

const isSelf = computed(() => Boolean(user.value) && me.value?.id === user.value?.id)
const locked = computed(() => (user.value ? usersIsLocked(user.value) : false))

const editOpen = ref(false)
const resetOpen = ref(false)

const toggle = useUsersConfirm(async (target: UserRead) => {
  const next = !target.is_active
  await api.setActive(target.id, next)
  toast.success(next ? `Usuario «${usersFullName(target)}» activado.` : `Usuario «${usersFullName(target)}» desactivado. Sus sesiones se cerraron.`)
  await detail.refresh()
})

const unlock = useUsersConfirm(async (target: UserRead) => {
  await api.unlock(target.id)
  toast.success(`Usuario «${usersFullName(target)}» desbloqueado.`)
  await detail.refresh()
})

const removal = useUsersConfirm(async (role: UserRoleRead) => {
  const updated = await api.removeRole(props.id, role.id)
  toast.success(`Rol «${role.name}» quitado.`)
  await detail.applyDetail(updated)
})

const deactivating = computed(() => toggle.target?.is_active ?? true)
</script>

<template>
  <div class="space-y-6">
    <div>
      <NuxtLink to="/users" class="text-sm text-primary-700 hover:underline">← Usuarios</NuxtLink>
    </div>

    <UiAlert v-if="error" :message="error" data-testid="detail-error" />
    <div v-else-if="loading && !user" class="flex items-center gap-2 text-text-muted"><UiSpinner size="md" color="primary" /> Cargando…</div>

    <template v-if="user">
      <UiPageHeader :title="usersFullName(user)" :description="user.username">
        <template #actions>
          <UsersStatusBadge :user="user" />
          <LeoCan tag="leo.users.edit">
            <UiButton variant="secondary" data-testid="user-edit" @click="editOpen = true">Editar</UiButton>
          </LeoCan>
          <LeoCan tag="leo.users.unlock">
            <UiButton v-if="locked" variant="secondary" data-testid="user-unlock" @click="unlock.ask(user)">Desbloquear</UiButton>
          </LeoCan>
          <LeoCan tag="leo.users.reset-password">
            <UiButton variant="secondary" data-testid="user-reset" @click="resetOpen = true">Restablecer contraseña</UiButton>
          </LeoCan>
          <LeoCan tag="leo.users.deactivate">
            <UiButton v-if="!isSelf" :variant="user.is_active ? 'danger' : 'primary'" data-testid="user-toggle" @click="toggle.ask(user)">
              {{ user.is_active ? 'Desactivar' : 'Activar' }}
            </UiButton>
          </LeoCan>
        </template>
      </UiPageHeader>

      <p v-if="isSelf" class="text-sm text-text-muted" data-testid="self-note">Este es tu propio usuario: no puedes desactivarlo.</p>

      <UiCard title="Datos del usuario">
        <dl class="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt class="font-medium text-text-muted">Usuario</dt>
            <dd class="mt-1"><code>{{ user.username }}</code></dd>
          </div>
          <div>
            <dt class="font-medium text-text-muted">Correo</dt>
            <dd class="mt-1" data-testid="user-email">{{ user.email }}</dd>
          </div>
          <div>
            <dt class="font-medium text-text-muted">Documento</dt>
            <dd class="mt-1">{{ usersDocument(user) }} <span class="text-text-muted">({{ USERS_DOCUMENT_LABELS[user.document_type] }})</span></dd>
          </div>
          <div>
            <dt class="font-medium text-text-muted">Último acceso</dt>
            <dd class="mt-1">{{ usersFormatDateTime(user.last_login_at) }}</dd>
          </div>
        </dl>
      </UiCard>

      <section class="space-y-4" aria-labelledby="roles-title">
        <div>
          <h3 id="roles-title" class="text-lg font-semibold text-text">Roles y acceso</h3>
          <p class="text-sm text-text-muted" data-testid="access-line">
            <template v-if="user.is_active && accessApps.length">Acceso a: <strong class="text-text">{{ accessApps.join(', ') }}</strong></template>
            <template v-else-if="!user.is_active">El usuario está inactivo: no puede entrar a ninguna aplicación.</template>
            <template v-else>Sin acceso a ninguna aplicación todavía: necesita al menos un rol activo en ella.</template>
          </p>
        </div>

        <UiAlert v-if="lookupError" variant="warning" :message="lookupError" data-testid="lookup-error" />

        <p v-if="!groups.length" class="text-sm text-text-muted" data-testid="no-roles">Este usuario aún no tiene roles.</p>
        <UiCard v-for="group in groups" :key="group.applicationId" :title="group.applicationName" padding="sm" data-testid="role-group">
          <ul class="divide-y divide-border">
            <li v-for="role in group.roles" :key="role.id" class="flex flex-wrap items-center justify-between gap-2 px-2 py-2" data-testid="user-role">
              <div>
                <span class="font-medium text-text">{{ role.name }}</span>
                <span class="ml-2"><UiStatusBadge :active="role.is_active" /></span>
              </div>
              <LeoCan tag="leo.users.assign-roles">
                <UiButton variant="danger-ghost" size="sm" data-testid="role-remove" @click="removal.ask(role)">Quitar</UiButton>
              </LeoCan>
            </li>
          </ul>
        </UiCard>

        <LeoCan tag="leo.users.assign-roles">
          <UsersRoleAssigner :user-id="user.id" :options="roleOptions" @assigned="detail.applyDetail($event)" />
        </LeoCan>
      </section>

      <section class="space-y-3" aria-labelledby="perms-title">
        <div>
          <h3 id="perms-title" class="text-lg font-semibold text-text">Permisos efectivos</h3>
          <p class="text-sm text-text-muted">Todo lo que puede hacer, según sus roles activos.</p>
        </div>
        <p v-if="!effective.length" class="text-sm text-text-muted" data-testid="no-permissions">Sin permisos: no tiene roles activos con permisos asignados.</p>
        <UiCard v-for="group in effective" :key="group.applicationId" :title="group.applicationName" padding="sm" data-testid="effective-group">
          <ul class="grid gap-x-6 gap-y-1 px-2 py-1 sm:grid-cols-2">
            <li v-for="perm in group.permissions" :key="perm.id" class="text-sm" data-testid="effective-permission">
              <span class="text-text">{{ perm.name }}</span>
              <code class="ml-2 text-xs text-text-muted">{{ perm.tag }}</code>
            </li>
          </ul>
        </UiCard>
      </section>

      <LeoCan tag="leo.users.edit">
        <UsersEditModal v-model:open="editOpen" :user="user" @saved="detail.refresh()" />
      </LeoCan>
      <LeoCan tag="leo.users.reset-password">
        <UsersResetPasswordModal v-model:open="resetOpen" :user="user" @saved="detail.refresh()" />
      </LeoCan>
    </template>

    <UiConfirmModal
      v-model:open="toggle.open"
      :title="deactivating ? 'Desactivar usuario' : 'Activar usuario'"
      :message="deactivating
        ? `Se desactivará a «${toggle.target ? usersFullName(toggle.target) : ''}» y se cerrarán todas sus sesiones abiertas. Podrás reactivarlo cuando quieras.`
        : `Se activará a «${toggle.target ? usersFullName(toggle.target) : ''}»: podrá volver a iniciar sesión.`"
      :confirm-label="deactivating ? 'Desactivar' : 'Activar'"
      :variant="deactivating ? 'danger' : 'primary'"
      :loading="toggle.loading"
      :error="toggle.error"
      @confirm="toggle.confirm()"
    />
    <UiConfirmModal
      v-model:open="unlock.open"
      title="Desbloquear usuario"
      :message="`Se borrarán los intentos fallidos y el bloqueo de «${unlock.target ? usersFullName(unlock.target) : ''}»: podrá intentar iniciar sesión de nuevo.`"
      confirm-label="Desbloquear"
      variant="primary"
      :loading="unlock.loading"
      :error="unlock.error"
      @confirm="unlock.confirm()"
    />
    <UiConfirmModal
      v-model:open="removal.open"
      title="Quitar rol"
      :message="`Se quitará el rol «${removal.target?.name ?? ''}» a este usuario: dejará de recibir sus permisos.`"
      confirm-label="Quitar rol"
      :loading="removal.loading"
      :error="removal.error"
      @confirm="removal.confirm()"
    />
  </div>
</template>
