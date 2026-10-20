import type { SessionPage, SessionsUserPage } from '../types/sessions'
import type { SessionsQueryInput } from '../utils/sessionQuery'
import { buildSessionsQuery } from '../utils/sessionQuery'

/** Máximo de `page_size` que acepta el backend (un solo viaje para el selector de usuarios). */
const USERS_PAGE_SIZE = 200

/**
 * Llamadas a `/auth/sessions` (y, de solo lectura, a `/users` para nombrar al
 * dueño de cada sesión y llenar el filtro): única puerta del módulo a la API.
 * Lanzan `LeoApiError`; quien las llama muestra `leoErrorMessage(err)`.
 */
export function useSessionsApi() {
  const api = useLeoApi()

  return {
    list: (input: SessionsQueryInput) => api<SessionPage>('/auth/sessions', { query: buildSessionsQuery(input) }),
    revoke: (id: string) => api<void>(`/auth/sessions/${id}/revoke`, { method: 'POST' }),
    listUsers: () => api<SessionsUserPage>('/users', { query: { page: 1, page_size: USERS_PAGE_SIZE } })
  }
}
