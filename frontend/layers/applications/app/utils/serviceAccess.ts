import { LeoApiError } from '#leo-client/lib/errors'
import type { ApplicationRead, ApplicationsServiceGrant, ApplicationsServiceGrantGroup } from '../types/applications'
import { isProtectedApp } from './actionTag'
import { applicationErrorMessage } from './applicationErrors'

const byName = (a: string, b: string) => a.localeCompare(b, 'es')

/** Agrupa las concesiones por aplicación destino (apps y roles ordenados por nombre). */
export function applicationsGroupServiceGrants(grants: readonly ApplicationsServiceGrant[]): ApplicationsServiceGrantGroup[] {
  const groups = new Map<string, ApplicationsServiceGrantGroup>()
  for (const grant of grants) {
    const group = groups.get(grant.application.id)
    if (group) group.grants.push(grant)
    else groups.set(grant.application.id, { application: grant.application, grants: [grant] })
  }
  const result = [...groups.values()]
  for (const group of result) group.grants.sort((a, b) => byName(a.role.name, b.role.name))
  return result.sort((a, b) => byName(a.application.name, b.application.name))
}

/** Aplicaciones que se pueden elegir como destino: ni la actual ni `leo`. */
export function applicationsGrantableTargets(apps: readonly ApplicationRead[], currentId: string): ApplicationRead[] {
  return apps.filter(app => app.id !== currentId && !isProtectedApp(app.slug))
}

/** Texto de confirmación al conceder. */
export function applicationsGrantSummary(appName: string, targetName: string): string {
  return `${appName} podrá consultar ${targetName} con los permisos de estos roles.`
}

const SERVICE_ACCESS_ERRORS: Record<string, string> = {
  same_application: 'Elige roles de otra aplicación: una app no necesita conceder acceso a sí misma.',
  role_inactive: 'Alguno de los roles elegidos está inactivo. Actívalo antes de concederlo o elige otro.',
  leo_app_not_grantable: 'Los roles de Leo no se pueden conceder a otras aplicaciones.',
  invalid_reference: 'Algunos roles ya no existen o cambiaron. Vuelve a abrir el diálogo e inténtalo de nuevo.'
}

/** Mensaje legible de un error de la concesión de acceso entre aplicaciones. */
export function applicationsServiceAccessErrorMessage(err: unknown): string {
  if (err instanceof LeoApiError && SERVICE_ACCESS_ERRORS[err.code]) return SERVICE_ACCESS_ERRORS[err.code]!
  return applicationErrorMessage(err)
}
