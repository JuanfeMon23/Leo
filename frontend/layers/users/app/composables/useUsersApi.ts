import type {
  UserCreatePayload,
  UserDetail,
  UserPage,
  UserRead,
  UsersApplicationPage,
  UsersRolePage,
  UsersRoleWithActions,
  UserUpdatePayload
} from '../types/users'
import type { UsersQueryInput } from '../utils/userQuery'
import { buildUsersQuery } from '../utils/userQuery'

/** Máximo de `page_size` que acepta el backend (un solo viaje para selectores). */
const LOOKUP_PAGE_SIZE = 200

/**
 * Llamadas a `/users` (y, de solo lectura, a `/applications` y `/roles` para
 * nombrar las apps y ofrecer los roles asignables): única puerta del módulo a
 * la API. Lanzan `LeoApiError`; quien las llama muestra `userErrorMessage(err)`.
 */
export function useUsersApi() {
  const api = useLeoApi()
  const base = '/users'
  const user = (id: string) => `${base}/${id}`

  return {
    list: (input: UsersQueryInput) => api<UserPage>(base, { query: buildUsersQuery(input) }),
    get: (id: string) => api<UserDetail>(user(id)),
    create: (body: UserCreatePayload) => api<UserRead>(base, { method: 'POST', body }),
    update: (id: string, body: UserUpdatePayload) => api<UserRead>(user(id), { method: 'PATCH', body }),
    setActive: (id: string, active: boolean) =>
      api<UserRead>(`${user(id)}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' }),
    unlock: (id: string) => api<UserRead>(`${user(id)}/unlock`, { method: 'POST' }),
    /** La contraseña solo viaja en este cuerpo; no se guarda ni se registra. */
    resetPassword: (id: string, password: string) =>
      api<UserRead>(`${user(id)}/reset-password`, { method: 'POST', body: { password } }),
    addRoles: (id: string, roleIds: string[]) =>
      api<UserDetail>(`${user(id)}/roles`, { method: 'POST', body: { role_ids: roleIds } }),
    removeRole: (id: string, roleId: string) =>
      api<UserDetail>(`${user(id)}/roles/${roleId}`, { method: 'DELETE' }),

    listApplications: () =>
      api<UsersApplicationPage>('/applications', { query: { page: 1, page_size: LOOKUP_PAGE_SIZE } }),
    listActiveRoles: () =>
      api<UsersRolePage>('/roles', { query: { page: 1, page_size: LOOKUP_PAGE_SIZE, active: true } }),
    getRole: (id: string) => api<UsersRoleWithActions>(`/roles/${id}`)
  }
}
