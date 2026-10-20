import { LeoApiError, leoErrorMessage } from '#leo-client/lib/errors'

/**
 * Mensaje legible de un error del módulo de usuarios. Los casos con texto
 * propio (`self_deactivation`, `weak_password`, `invalid_reference`) se
 * explican aquí; el resto va por `leoErrorMessage` (mensaje del backend en
 * 4xx, genérico en red/5xx). Nunca la respuesta cruda.
 */
export function userErrorMessage(err: unknown): string {
  if (err instanceof LeoApiError) {
    if (err.code === 'self_deactivation') {
      return 'No puedes desactivar tu propio usuario. Pídele a otra persona administradora que lo haga.'
    }
    if (err.code === 'weak_password') {
      return 'La contraseña es débil: no cumple la política de seguridad. Revisa los requisitos e inténtalo de nuevo.'
    }
    if (err.code === 'invalid_reference') {
      return 'Alguno de los roles ya no existe o cambió. Recarga la página e inténtalo de nuevo.'
    }
  }
  return leoErrorMessage(err)
}
