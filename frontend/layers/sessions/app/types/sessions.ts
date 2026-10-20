// Tipos del contrato `/api/v1/auth/sessions` (fuente: backend/app/modules/auth/schemas.py, `SessionRead`)
// y de lo que el módulo lee de `/users` para nombrar a la persona.

export type SessionRevokedReason = 'logout' | 'admin' | 'user-deactivated' | 'refresh-reuse' | 'idle-timeout'

export interface SessionRead {
  id: string
  user_id: string
  ip: string | null
  user_agent: string | null
  created_at: string
  last_activity_at: string
  expires_at: string
  revoked_at: string | null
  /** Motivo de revocación; texto abierto por si el backend suma uno nuevo. */
  revoked_reason: string | null
  is_current: boolean
}

export interface SessionPage {
  items: SessionRead[]
  total: number
  page: number
  page_size: number
}

export type SessionStatusKind = 'active' | 'idle' | 'revoked'

export interface SessionStatus {
  kind: SessionStatusKind
  /** «Activa», «Inactiva por tiempo» o «Revocada». */
  label: string
  /** Motivo legible (solo revocadas). */
  reason: string | null
}

/** Usuario para el filtro y para nombrar al dueño de cada sesión. */
export interface SessionsUser {
  id: string
  username: string
  first_name: string
  last_name: string
}

export interface SessionsUserPage {
  items: SessionsUser[]
  total: number
  page: number
  page_size: number
}
