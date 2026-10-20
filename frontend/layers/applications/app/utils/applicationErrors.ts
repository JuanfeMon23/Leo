import { LeoApiError, leoErrorMessage } from '#leo-client/lib/errors'

/**
 * Mensaje legible de un error del módulo de aplicaciones. `leo_app_protected`
 * (409) tiene texto propio; el resto va por `leoErrorMessage` (mensaje del
 * backend en 4xx, genérico en red/5xx). Nunca la respuesta cruda.
 */
export function applicationErrorMessage(err: unknown): string {
  if (err instanceof LeoApiError && err.code === 'leo_app_protected') {
    return 'La aplicación Leo no se puede modificar desde aquí: la mantiene el sistema (sin ella se perdería el acceso a la administración).'
  }
  return leoErrorMessage(err)
}
