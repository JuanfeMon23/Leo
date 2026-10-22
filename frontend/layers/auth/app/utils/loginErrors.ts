import { LeoApiError, leoErrorMessage } from '#leo-client/lib/errors'
import { formatWait } from '../../../../app/utils/formatWait'

/** Mensaje del login: 429 con el tiempo restante; el resto, legible vía leo-client. */
export function loginErrorMessage(err: unknown): string {
  if (err instanceof LeoApiError && err.status === 429) {
    return err.retryAfterSeconds
      ? `Demasiados intentos fallidos. Inténtalo de nuevo en ${formatWait(err.retryAfterSeconds)}.`
      : 'Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.'
  }
  return leoErrorMessage(err)
}

const REASONS: Record<string, string> = {
  idle: 'Tu sesión se cerró por inactividad. Inicia sesión de nuevo.',
  expired: 'Tu sesión expiró. Inicia sesión de nuevo.'
}

/** Por qué se cerró la sesión (`?reason=`); solo valores conocidos, nunca texto de la URL. */
export function loginReasonMessage(reason: unknown): string | null {
  return typeof reason === 'string' && Object.hasOwn(REASONS, reason) ? REASONS[reason]! : null
}
