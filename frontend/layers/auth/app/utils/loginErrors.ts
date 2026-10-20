import { LeoApiError, leoErrorMessage } from '#leo-client/lib/errors'

function plural(n: number, unit: string): string {
  return `${n} ${unit}${n === 1 ? '' : 's'}`
}

/** "45 segundos", "2 minutos", "1 hora": espera legible (se redondea hacia arriba). */
export function formatWait(seconds: number): string {
  if (seconds < 60) return plural(Math.max(1, Math.ceil(seconds)), 'segundo')
  if (seconds < 3600) return plural(Math.ceil(seconds / 60), 'minuto')
  return plural(Math.ceil(seconds / 3600), 'hora')
}

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
