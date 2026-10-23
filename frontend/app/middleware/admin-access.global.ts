import { NO_ACCESS_PATH, hasAdminAccess, isAdminRoute } from '../utils/adminAccess'

/**
 * Guardia del panel: toda ruta administrativa exige al menos un permiso `leo.*`
 * (además del tag propio de cada página, que valida leo-client). Quien tenga sesión
 * pero ningún `leo.*` (p. ej. pacientes que entran por el SSO) va a «Sin acceso».
 * Sin sesión no decide: de eso se ocupa el middleware de leo-client.
 */
export default defineNuxtRouteMiddleware(async (to) => {
  if (to.meta.leo?.public || !isAdminRoute(to.path)) return
  const session = useLeoSession()
  try {
    await session.ensure()
  } catch {
    return // sin respuesta del servidor lo resuelve el middleware de leo-client
  }
  if (!session.isAuthenticated.value) return
  if (!hasAdminAccess(session.permissions.value)) return navigateTo(NO_ACCESS_PATH, { replace: true })
})
