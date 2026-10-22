import type { LeoMe } from '#leo-client/lib/types'
import type { ProfilePasswordPayload, ProfileUpdatePayload } from '../types/profile'

/**
 * Llamadas a `/auth/me/*` (autogestión: cookie SSO + DPoP, sin permiso `leo.*`):
 * única puerta del módulo a la API. Lanzan `LeoApiError`.
 */
export function useProfileApi() {
  const api = useLeoApi()

  return {
    /** Devuelve la sesión actualizada (`MeResponse`) para refrescar el estado local. */
    update: (body: ProfileUpdatePayload) =>
      api<LeoMe>('/auth/me/profile', { method: 'PATCH', body }),
    /**
     * La contraseña solo viaja en este cuerpo; no se guarda ni se registra.
     * `skipSessionHandling`: el 401 `invalid_credentials` (contraseña actual
     * incorrecta) no es una sesión caducada y no debe llevar al login.
     */
    changePassword: (body: ProfilePasswordPayload) =>
      api<void>('/auth/me/password', { method: 'POST', body, skipSessionHandling: true })
  }
}
