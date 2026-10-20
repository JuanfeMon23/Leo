import type { SessionRead, SessionsUser, SessionStatus, SessionStatusKind } from '../types/sessions'

const REASON_LABELS: Record<string, string> = {
  'logout': 'Cierre de sesión',
  'admin': 'Revocada por un administrador',
  'user-deactivated': 'Usuario desactivado',
  'refresh-reuse': 'Reúso de token (posible robo)',
  'idle-timeout': 'Inactividad'
}

/** Motivo de revocación en lenguaje de persona; uno desconocido se muestra tal cual. */
export function sessionRevokedReasonLabel(reason: string | null | undefined): string | null {
  if (!reason) return null
  return REASON_LABELS[reason] ?? reason
}

/**
 * Estado de una sesión: «Revocada» (con motivo) manda sobre todo; si no está
 * revocada y ya venció, «Inactiva por tiempo»; si no, «Activa».
 */
export function sessionStatus(s: Pick<SessionRead, 'revoked_at' | 'revoked_reason' | 'expires_at'>, now: Date = new Date()): SessionStatus {
  if (s.revoked_at) return { kind: 'revoked', label: 'Revocada', reason: sessionRevokedReasonLabel(s.revoked_reason) }
  if (new Date(s.expires_at).getTime() <= now.getTime()) return { kind: 'idle', label: 'Inactiva por tiempo', reason: null }
  return { kind: 'active', label: 'Activa', reason: null }
}

const VARIANTS: Record<SessionStatusKind, 'success' | 'neutral' | 'danger'> = { active: 'success', idle: 'neutral', revoked: 'danger' }
export const sessionStatusVariant = (kind: SessionStatusKind) => VARIANTS[kind]

/** Solo tiene sentido revocar una sesión activa. */
export const sessionCanRevoke = (s: Pick<SessionRead, 'revoked_at' | 'revoked_reason' | 'expires_at'>, now: Date = new Date()) =>
  sessionStatus(s, now).kind === 'active'

/** Dueño de la sesión: nombre completo y usuario; desconocido si no está en la lista cargada. */
export function sessionOwnerLabel(userId: string, users: readonly SessionsUser[]): { name: string, username: string | null } {
  const user = users.find(u => u.id === userId)
  if (!user) return { name: 'Usuario desconocido', username: null }
  return { name: `${user.first_name} ${user.last_name}`.trim() || user.username, username: user.username }
}
