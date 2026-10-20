import type { LeoRequestOptions } from '../lib/transport'

/**
 * Cliente HTTP de la app: cada petición va firmada (DPoP) y con credenciales
 * por el transporte configurado. Lanza `LeoApiError`; para mostrarlo usa
 * `leoErrorMessage(err)`. Un 401 de sesión lleva solo al login.
 */
export function useLeoApi() {
  const { $leo } = useNuxtApp()
  return <T = unknown>(path: string, options?: LeoRequestOptions) => $leo.transport.request<T>(path, options)
}
