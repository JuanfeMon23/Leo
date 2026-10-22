import { LeoApiError, leoErrorMessage } from '#leo-client/lib/errors'
import { formatWait } from '../../../../app/utils/formatWait'

/** Errores de cambio de contraseña repartidos por campo y un error general. */
export interface ProfilePasswordErrors {
  fields: Partial<Record<'current_password' | 'new_password', string>>
  form: string | null
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string' && v.length > 0) : []
}

/**
 * Traduce el error de `POST /auth/me/password`:
 * - `invalid_credentials` (401) → campo «contraseña actual» (no es sesión caducada);
 * - `weak_password` → campo «contraseña nueva», con los requisitos incumplidos;
 * - `same_password` → campo «contraseña nueva»;
 * - 429 → error general con la espera; el resto → `leoErrorMessage`.
 * Nunca la respuesta cruda.
 */
export function profilePasswordErrors(err: unknown): ProfilePasswordErrors {
  if (err instanceof LeoApiError) {
    if (err.code === 'invalid_credentials') {
      return { fields: { current_password: err.message || 'La contraseña actual no es correcta.' }, form: null }
    }
    if (err.code === 'weak_password') {
      const missing = asStrings((err.details as { password?: unknown } | null)?.password)
      const message = missing.length
        ? `La contraseña no cumple la política: ${missing.map(m => m.charAt(0).toLowerCase() + m.slice(1)).join('; ')}.`
        : 'La contraseña es débil: no cumple la política de seguridad. Revisa los requisitos.'
      return { fields: { new_password: message }, form: null }
    }
    if (err.code === 'same_password') {
      return { fields: { new_password: 'La contraseña nueva debe ser distinta de la actual.' }, form: null }
    }
    if (err.status === 429) {
      return {
        fields: {},
        form: err.retryAfterSeconds
          ? `Demasiados intentos. Inténtalo de nuevo en ${formatWait(err.retryAfterSeconds)}.`
          : 'Demasiados intentos. Espera unos minutos e inténtalo de nuevo.'
      }
    }
  }
  return { fields: {}, form: leoErrorMessage(err) }
}
