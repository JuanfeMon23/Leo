import type { UserRead, UsersStatus } from '../types/users'

const pad = (n: number) => String(n).padStart(2, '0')

export const usersFullName = (u: Pick<UserRead, 'first_name' | 'last_name'>) => `${u.first_name} ${u.last_name}`.trim()

export const usersDocument = (u: Pick<UserRead, 'document_type' | 'document_number'>) =>
  `${u.document_type} ${u.document_number}`

/** `DD/MM/AAAA HH:MM` en hora local; sin fecha (o inválida) → «Nunca». */
export function usersFormatDateTime(iso: string | null | undefined): string {
  if (!iso) return 'Nunca'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'Nunca'
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** El bloqueo está vigente si `locked_until` es futuro. */
export function usersIsLocked(u: Pick<UserRead, 'locked_until'>, now: Date = new Date()): boolean {
  return Boolean(u.locked_until) && new Date(u.locked_until as string).getTime() > now.getTime()
}

/**
 * Estado legible: inactivo manda sobre bloqueado; «Bloqueado hasta HH:MM»
 * (con la fecha si no es hoy).
 */
export function usersStatus(u: Pick<UserRead, 'is_active' | 'locked_until'>, now: Date = new Date()): UsersStatus {
  if (!u.is_active) return { kind: 'inactive', label: 'Inactivo' }
  if (usersIsLocked(u, now)) {
    const until = new Date(u.locked_until as string)
    const sameDay = until.toDateString() === now.toDateString()
    const time = `${pad(until.getHours())}:${pad(until.getMinutes())}`
    return { kind: 'locked', label: sameDay ? `Bloqueado hasta ${time}` : `Bloqueado hasta ${usersFormatDateTime(u.locked_until)}` }
  }
  return { kind: 'active', label: 'Activo' }
}
