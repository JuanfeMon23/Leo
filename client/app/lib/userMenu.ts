import type { LeoUser } from './types'
import type { LeoTransportKind } from './transport'

/** Nombre a mostrar: nombre + apellido, luego `name`, luego `username`. */
export function userDisplayName(user: Partial<LeoUser> | null | undefined): string {
  if (!user) return ''
  const full = `${user.first_name ?? ''} ${user.last_name ?? ''}`.trim()
  return full || (user.name ?? '').trim() || user.username || ''
}

/** Hasta dos iniciales (primeras dos palabras); `?` si no hay nombre. */
export function userInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (!words.length) return '?'
  return words.slice(0, 2).map(w => Array.from(w)[0]!.toLocaleUpperCase('es')).join('')
}

/** Inicial (una letra) del avatar de una app; `?` si no hay nombre. */
export function appInitial(name: string): string {
  const first = Array.from(name.trim())[0]
  return first ? first.toLocaleUpperCase('es') : '?'
}

/**
 * Destino de "Mi perfil". `leo-direct`: ruta interna; `bff`: página de perfil
 * de Leo con `return` = URL de la app actual (nada más). `null` = sin enlace.
 */
export function buildProfileUrl(
  config: { transport: LeoTransportKind, leoUrl?: string },
  currentUrl: string
): string | null {
  if (config.transport === 'leo-direct') return '/profile'
  const base = (config.leoUrl ?? '').trim().replace(/\/+$/, '')
  if (!/^https?:\/\//i.test(base)) return null
  return `${base}/profile?return=${encodeURIComponent(currentUrl)}`
}
