export const SESSIONS_PAGE_SIZE = 20

export interface SessionsQueryInput {
  /** `''` = las sesiones propias (el backend así lo interpreta). */
  userId: string
  activeOnly: boolean
  page: number
}

/**
 * Query de `GET /auth/sessions`. `active_only` va siempre explícito: el
 * backend lo asume `true` y «ver todas» exige mandarlo en `false`.
 */
export function buildSessionsQuery(input: SessionsQueryInput) {
  return {
    page: input.page,
    page_size: SESSIONS_PAGE_SIZE,
    active_only: input.activeOnly,
    ...(input.userId ? { user_id: input.userId } : {})
  }
}
