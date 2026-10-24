import { leoErrorMessage } from '../lib/errors'
import { LOGIN_LOOP_MESSAGE, loginLoopGuard } from '../lib/loginGuard'
import { hasPermission } from '../lib/permissions'

/**
 * Toda página exige sesión salvo `definePageMeta({ leo: { public: true } })`.
 * Con `leo: { tag }` exige además el/los tag(s) (`mode: 'any'` para basta
 * uno): sin permiso, la página 403 de leo-client.
 */
export default defineNuxtRouteMiddleware(async (to) => {
  const meta = to.meta.leo
  if (meta?.public) return

  const session = useLeoSession()
  try {
    await session.ensure()
  } catch (err) {
    // Sin respuesta del servidor no se puede saber si hay sesión: error legible, sin bucles.
    return abortNavigation(createError({ statusCode: 503, statusMessage: leoErrorMessage(err), fatal: true }))
  }

  if (!session.isAuthenticated.value) {
    // SSO vigente pero la app rechaza la sesión sin parar: cortar el bucle.
    if (!loginLoopGuard.attempt()) {
      return abortNavigation(createError({ statusCode: 401, statusMessage: LOGIN_LOOP_MESSAGE, fatal: true }))
    }
    try {
      const location = await useNuxtApp().$leo.transport.login(to.fullPath)
      return navigateTo(location.url, { external: location.external, replace: true })
    } catch (err) {
      // En `bff` el login pide la URL al backend: si no responde, error legible, sin bucles.
      return abortNavigation(createError({ statusCode: 503, statusMessage: leoErrorMessage(err), fatal: true }))
    }
  }

  if (meta?.tag !== undefined && !hasPermission(session.permissions.value, meta.tag, meta.mode)) {
    return navigateTo({ path: '/leo/forbidden', query: { from: to.fullPath } }, { replace: true })
  }
})
