import type {
  UserRoleRead,
  UsersApplication,
  UsersEffectiveGroup,
  UsersRoleGroup,
  UsersRoleOption,
  UsersRoleWithActions
} from '../types/users'

const UNKNOWN_APP = 'Aplicación desconocida'
const byText = (a: string, b: string) => a.localeCompare(b, 'es')

const appName = (apps: UsersApplication[], id: string) => apps.find(a => a.id === id)?.name ?? UNKNOWN_APP

/** Roles de un usuario agrupados por aplicación (apps y roles en orden alfabético). */
export function usersGroupRolesByApp(roles: UserRoleRead[], apps: UsersApplication[]): UsersRoleGroup[] {
  const byApp = new Map<string, UserRoleRead[]>()
  for (const r of roles) byApp.set(r.application_id, [...(byApp.get(r.application_id) ?? []), r])
  return [...byApp.entries()]
    .map(([applicationId, list]) => ({
      applicationId,
      applicationName: appName(apps, applicationId),
      roles: [...list].sort((a, b) => byText(a.name, b.name)),
      hasAccess: list.some(r => r.is_active)
    }))
    .sort((a, b) => byText(a.applicationName, b.applicationName))
}

/** Nombres de las aplicaciones a las que el usuario accede (≥1 rol activo en ellas). */
export const usersAccessApps = (groups: UsersRoleGroup[]) => groups.filter(g => g.hasAccess).map(g => g.applicationName)

/**
 * Opciones del selector «Aplicación → Rol»: solo roles activos de apps
 * activas que el usuario aún no tiene.
 */
export function usersRoleOptions(roles: UsersRoleOption[], apps: UsersApplication[], assigned: Set<string>) {
  const activeApps = new Map(apps.filter(a => a.is_active).map(a => [a.id, a.name]))
  return roles
    .filter(r => r.is_active && activeApps.has(r.application_id) && !assigned.has(r.id))
    .map(r => ({ app: activeApps.get(r.application_id) as string, role: r.name, value: r.id }))
    .sort((a, b) => byText(a.app, b.app) || byText(a.role, b.role))
    .map(o => ({ value: o.value, label: `${o.app} → ${o.role}` }))
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
    for (const a of role.actions) {
      if (a.is_active && !bucket.has(a.id)) bucket.set(a.id, { id: a.id, name: a.name, tag: a.tag })
    }
    byApp.set(role.application_id, bucket)
  }
  return [...byApp.entries()]
    .filter(([, bucket]) => bucket.size > 0)
    .map(([applicationId, bucket]) => ({
      applicationId,
      applicationName: appName(apps, applicationId),
      permissions: [...bucket.values()].sort((a, b) => byText(a.name, b.name))
    }))
    .sort((a, b) => byText(a.applicationName, b.applicationName))
}
