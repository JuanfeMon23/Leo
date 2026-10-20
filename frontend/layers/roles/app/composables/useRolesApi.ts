import type {
  RoleCreatePayload,
  RoleDetail,
  RolePage,
  RoleRead,
  RolesApplicationPage,
  RolesCatalog,
  RoleUpdatePayload
} from '../types/roles'
import type { RolesQueryInput } from '../utils/roleQuery'
import { buildRolesQuery } from '../utils/roleQuery'

/** Máximo de `page_size` que acepta el backend (un solo viaje para el selector de aplicaciones). */
const APPLICATIONS_PAGE_SIZE = 200

/**
 * Llamadas a `/roles` (y, de solo lectura, a `/applications` para el selector
 * y el catálogo de permisos): única puerta del módulo a la API. Lanzan
 * `LeoApiError`; quien las llama muestra `roleErrorMessage(err)`.
 */
export function useRolesApi() {
  const api = useLeoApi()
  const base = '/roles'
  const role = (id: string) => `${base}/${id}`

  return {
    list: (input: RolesQueryInput) => api<RolePage>(base, { query: buildRolesQuery(input) }),
    get: (id: string) => api<RoleDetail>(role(id)),
    create: (body: RoleCreatePayload) => api<RoleRead>(base, { method: 'POST', body }),
    update: (id: string, body: RoleUpdatePayload) => api<RoleRead>(role(id), { method: 'PATCH', body }),
    setActive: (id: string, active: boolean) =>
      api<RoleRead>(`${role(id)}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' }),

    /** Asigna acciones (todas de la app del rol); devuelve el rol con sus acciones. */
    addActions: (id: string, actionIds: string[]) =>
      api<RoleDetail>(`${role(id)}/actions`, { method: 'POST', body: { action_ids: actionIds } }),
    /** Quita una acción asignada; devuelve el rol con sus acciones. */
    removeAction: (id: string, actionId: string) =>
      api<RoleDetail>(`${role(id)}/actions/${actionId}`, { method: 'DELETE' }),

    listApplications: () =>
      api<RolesApplicationPage>('/applications', { query: { page: 1, page_size: APPLICATIONS_PAGE_SIZE } }),
    getCatalog: (applicationId: string) => api<RolesCatalog>(`/applications/${applicationId}`)
  }
}
