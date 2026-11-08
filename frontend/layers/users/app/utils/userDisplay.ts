import type { UserRead, UsersStatus } from '../types/users'

const pad = (value: number) => String(value).padStart(2, '0')

export const usersFullName = (user: Pick<UserRead, 'first_name' | 'last_name'>) => `${user.first_name} ${user.last_name}`.trim()

export const usersDocument = (user: Pick<UserRead, 'document_type' | 'document_number'>) =>
  `${user.document_type} ${user.document_number}`

/** `DD/MM/AAAA HH:MM` en hora local; sin fecha (o inválida) → «Nunca». */
export function usersFormatDateTime(iso: string | null | undefined): string {
  if (!iso) return 'Nunca'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'Nunca'
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** El bloqueo está vigente si `locked_until` es futuro. */
export function usersIsLocked(user: Pick<UserRead, 'locked_until'>, now: Date = new Date()): boolean {
  return Boolean(user.locked_until) && new Date(user.locked_until as string).getTime() > now.getTime()
}

/**
 * Estado legible: inactivo manda sobre bloqueado; «Bloqueado hasta HH:MM»
 * (con la fecha si no es hoy).
 */
export function usersStatus(user: Pick<UserRead, 'is_active' | 'locked_until'>, now: Date = new Date()): UsersStatus {
  if (!user.is_active) return { kind: 'inactive', label: 'Inactivo' }
  if (usersIsLocked(user, now)) {
    const until = new Date(user.locked_until as string)
    const sameDay = until.toDateString() === now.toDateString()
    const time = `${pad(until.getHours())}:${pad(until.getMinutes())}`
    return { kind: 'locked', label: sameDay ? `Bloqueado hasta ${time}` : `Bloqueado hasta ${usersFormatDateTime(user.locked_until)}` }
  }
  return { kind: 'active', label: 'Activo' }
}
