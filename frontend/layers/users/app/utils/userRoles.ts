import type {
  UserRoleRead,
  UsersApplication,
  UsersEffectiveGroup,
  UsersRoleGroup,
  UsersRoleOption,
  UsersRoleWithActions
} from '../types/users'

const UNKNOWN_APP = 'Aplicación desconocida'
const byText = (left: string, right: string) => left.localeCompare(right, 'es')

const appName = (apps: UsersApplication[], id: string) => apps.find(application => application.id === id)?.name ?? UNKNOWN_APP

/** Roles de un usuario agrupados por aplicación (apps y roles en orden alfabético). */
export function usersGroupRolesByApp(roles: UserRoleRead[], apps: UsersApplication[]): UsersRoleGroup[] {
  const byApp = new Map<string, UserRoleRead[]>()
  for (const result of roles) byApp.set(result.application_id, [...(byApp.get(result.application_id) ?? []), result])
  return [...byApp.entries()]
    .map(([applicationId, list]) => ({
      applicationId,
      applicationName: appName(apps, applicationId),
      roles: [...list].sort((left, right) => byText(left.name, right.name)),
      hasAccess: list.some(result => result.is_active)
    }))
    .sort((left, right) => byText(left.applicationName, right.applicationName))
}

/** Nombres de las aplicaciones a las que el usuario accede (≥1 rol activo en ellas). */
export const usersAccessApps = (groups: UsersRoleGroup[]) => groups.filter(group => group.hasAccess).map(group => group.applicationName)

/**
 * Opciones del selector «Aplicación → Rol»: solo roles activos de apps
 * activas que el usuario aún no tiene.
 */
export function usersRoleOptions(roles: UsersRoleOption[], apps: UsersApplication[], assigned: Set<string>) {
  const activeApps = new Map(apps.filter(application => application.is_active).map(application => [application.id, application.name]))
  return roles
    .filter(role => role.is_active && activeApps.has(role.application_id) && !assigned.has(role.id))
    .map(role => ({ app: activeApps.get(role.application_id) as string, role: role.name, value: role.id }))
    .sort((left, right) => byText(left.app, right.app) || byText(left.role, right.role))
    .map(option => ({ value: option.value, label: `${option.app} → ${option.role}` }))
}

/**
 * Permisos efectivos del usuario: unión de las acciones activas de sus roles
 * activos, sin repetir, por aplicación. Se muestran con el `name` legible.
 */
export function usersEffectivePermissions(roles: UsersRoleWithActions[], apps: UsersApplication[]): UsersEffectiveGroup[] {
  const byApp = new Map<string, Map<string, { id: string, name: string, tag: string }>>()
  for (const role of roles) {
    if (!role.is_active) continue
    const bucket = byApp.get(role.application_id) ?? new Map()
    for (const action of role.actions) {
      if (action.is_active && !bucket.has(action.id)) bucket.set(action.id, { id: action.id, name: action.name, tag: action.tag })
    }
    byApp.set(role.application_id, bucket)
  }
  return [...byApp.entries()]
    .filter(([, bucket]) => bucket.size > 0)
    .map(([applicationId, bucket]) => ({
      applicationId,
      applicationName: appName(apps, applicationId),
      permissions: [...bucket.values()].sort((left, right) => byText(left.name, right.name))
    }))
    .sort((left, right) => byText(left.applicationName, right.applicationName))
}
