import type {
  ApplicationActionRead,
  ApplicationCreated,
  ApplicationDetail,
  ApplicationModuleRead,
  ApplicationPage,
  ApplicationPayload,
  ApplicationRead,
  ApplicationSecretRotated,
  ApplicationsGrantPermission,
  ApplicationsRolePage,
  ApplicationsServiceGrant
} from '../types/applications'
import type { ApplicationsQueryInput } from '../utils/applicationQuery'
import { buildApplicationsQuery } from '../utils/applicationQuery'

/** Máximo de `page_size` que acepta el backend (un solo viaje para los selectores). */
const SERVICE_LOOKUP_PAGE_SIZE = 200

/**
 * Llamadas a `/applications` (única puerta del módulo a la API). Lanzan
 * `LeoApiError`; quien las llama muestra `applicationErrorMessage(err)`.
 * Los secretos que devuelven (`create`, `rotateSecret`) NO se guardan aquí.
 */
export function useApplicationsApi() {
  const api = useLeoApi()
  const base = '/applications'
  const app = (id: string) => `${base}/${id}`

  return {
    list: (input: ApplicationsQueryInput) => api<ApplicationPage>(base, { query: buildApplicationsQuery(input) }),
    get: (id: string) => api<ApplicationDetail>(app(id)),
    create: (body: ApplicationPayload) => api<ApplicationCreated>(base, { method: 'POST', body }),
    update: (id: string, body: Partial<ApplicationPayload>) => api<ApplicationRead>(app(id), { method: 'PATCH', body }),
    setActive: (id: string, active: boolean) =>
      api<ApplicationRead>(`${app(id)}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' }),
    rotateSecret: (id: string) => api<ApplicationSecretRotated>(`${app(id)}/rotate-secret`, { method: 'POST' }),

    createModule: (id: string, body: { slug: string, name: string, description: string | null }) =>
      api<ApplicationModuleRead>(`${app(id)}/modules`, { method: 'POST', body }),
    updateModule: (id: string, moduleId: string, body: { name: string, description: string | null }) =>
      api<ApplicationModuleRead>(`${app(id)}/modules/${moduleId}`, { method: 'PATCH', body }),
    setModuleActive: (id: string, moduleId: string, active: boolean) =>
      api<ApplicationModuleRead>(`${app(id)}/modules/${moduleId}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' }),

    createAction: (id: string, moduleId: string, body: { verb: string, name: string, description: string | null }) =>
      api<ApplicationActionRead>(`${app(id)}/modules/${moduleId}/actions`, { method: 'POST', body }),
    updateAction: (id: string, actionId: string, body: { name: string, description: string | null }) =>
      api<ApplicationActionRead>(`${app(id)}/actions/${actionId}`, { method: 'PATCH', body }),
    setActionActive: (id: string, actionId: string, active: boolean) =>
      api<ApplicationActionRead>(`${app(id)}/actions/${actionId}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' }),

    // Acceso entre aplicaciones (credenciales de servicio).
    listServiceAccess: (id: string) => api<ApplicationsServiceGrant[]>(`${app(id)}/service-access`),
    grantServiceAccess: (id: string, roleIds: string[]) =>
      api<ApplicationsServiceGrant[]>(`${app(id)}/service-access`, { method: 'POST', body: { role_ids: roleIds } }),
    revokeServiceAccess: (id: string, roleId: string) =>
      api<unknown>(`${app(id)}/service-access/${roleId}`, { method: 'DELETE' }),
    /** Todas las apps (un viaje) para elegir el destino. */
    listAllApplications: () => api<ApplicationPage>(base, { query: { page: 1, page_size: SERVICE_LOOKUP_PAGE_SIZE } }),
    /** Roles ACTIVOS de una app (solo lectura, para elegir qué conceder). */
    listActiveRoles: (applicationId: string) =>
      api<ApplicationsRolePage>('/roles', { query: { application_id: applicationId, active: true, page: 1, page_size: SERVICE_LOOKUP_PAGE_SIZE } }),
    /** Permisos de un rol (`GET /roles/{id}`). */
    getRolePermissions: async (roleId: string) =>
      (await api<{ actions: ApplicationsGrantPermission[] }>(`/roles/${roleId}`)).actions
  }
}
