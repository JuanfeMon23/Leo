import type { UserDetail, UsersApplication, UsersRoleOption, UsersRoleWithActions } from '../types/users'
import { userErrorMessage } from '../utils/userErrors'
import { usersAccessApps, usersEffectivePermissions, usersGroupRolesByApp, usersRoleOptions } from '../utils/userRoles'

/**
 * Estado del detalle de un usuario: sus datos y roles (`GET /users/{id}`), las
 * aplicaciones (para nombrar y agrupar), los roles activos asignables y, por
 * cada rol activo suyo, sus acciones (permisos efectivos). Lo secundario
 * (apps, roles, permisos) falla sin tumbar el detalle: se avisa aparte.
 */
export function useUsersDetail(userId: () => string) {
  const api = useUsersApi()

  const user = ref<UserDetail | null>(null)
  const applications = ref<UsersApplication[]>([])
  const allRoles = ref<UsersRoleOption[]>([])
  const roleDetails = ref<UsersRoleWithActions[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lookupError = ref<string | null>(null)

  const groups = computed(() => usersGroupRolesByApp(user.value?.roles ?? [], applications.value))
  const accessApps = computed(() => usersAccessApps(groups.value))
  const roleOptions = computed(() =>
    usersRoleOptions(allRoles.value, applications.value, new Set((user.value?.roles ?? []).map(r => r.id)))
  )
  const effective = computed(() => usersEffectivePermissions(roleDetails.value, applications.value))

  async function loadEffective() {
    const active = (user.value?.roles ?? []).filter(r => r.is_active)
    const results = await Promise.allSettled(active.map(r => api.getRole(r.id)))
    roleDetails.value = results.flatMap(r => (r.status === 'fulfilled' ? [r.value] : []))
    if (results.some(r => r.status === 'rejected')) {
      lookupError.value = 'No se pudieron cargar todos los permisos de sus roles.'
    }
  }

  async function loadLookups() {
    lookupError.value = null
    const [apps, roles] = await Promise.allSettled([api.listApplications(), api.listActiveRoles()])
    if (apps.status === 'fulfilled') applications.value = apps.value.items
    if (roles.status === 'fulfilled') allRoles.value = roles.value.items
    const failed = [apps, roles].find((r): r is PromiseRejectedResult => r.status === 'rejected')
    if (failed) {
      lookupError.value = `No se pudo cargar la lista de aplicaciones y roles: ${userErrorMessage(failed.reason)}`
    }
    await loadEffective()
  }

  async function load() {
    loading.value = true
    error.value = null
    try {
      user.value = await api.get(userId())
    } catch (err) {
      user.value = null
      error.value = userErrorMessage(err)
      loading.value = false
      return
    }
    loading.value = false
    await loadLookups()
  }

  /** Recarga solo el usuario (tras editarlo, activarlo, desbloquearlo…) y sus permisos. */
  async function refresh() {
    user.value = await api.get(userId())
    await loadEffective()
  }

  /** Toma la respuesta de una asignación/retiro de roles y recalcula los permisos. */
  async function applyDetail(detail: UserDetail) {
    user.value = detail
    await loadEffective()
  }

  return { user, applications, groups, accessApps, roleOptions, effective, loading, error, lookupError, load, refresh, applyDetail }
}
