import { LeoApiError, leoErrorMessage } from '#leo-client/lib/errors'

/**
 * Mensaje legible de un error del módulo de roles. `invalid_reference` (422 al
 * asignar) tiene texto propio; el resto va por `leoErrorMessage` (mensaje del
 * backend en 4xx, genérico en red/5xx). Nunca la respuesta cruda.
 */
export function roleErrorMessage(err: unknown): string {
  if (err instanceof LeoApiError && err.code === 'invalid_reference') {
    return 'Algunos permisos ya no están disponibles para este rol (cambiaron en la aplicación). Recarga la página e inténtalo de nuevo.'
  }
  return leoErrorMessage(err)
}
