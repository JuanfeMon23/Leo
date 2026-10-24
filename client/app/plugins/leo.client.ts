import { createDpopSigner, indexedDbDpopKeyStore, memoryDpopKeyStore } from '../lib/dpop'
import { broadcastIdleChannel, createIdleTracker } from '../lib/idleTracker'
import type { IdleLogoutReason, IdleTracker } from '../lib/idleTracker'
import { leoErrorMessage } from '../lib/errors'
import { LOGIN_LOOP_MESSAGE, loginLoopGuard } from '../lib/loginGuard'
import { createForbiddenHandler } from '../lib/forbiddenRefresh'
import { createLoginRedirector } from '../lib/loginRedirect'
import { createLeoBffTransport, createLeoDirectTransport } from '../lib/transport'
import type { LeoTransport } from '../lib/transport'

const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'scroll', 'wheel', 'touchstart'] as const

/**
 * Arranque de leo-client en el navegador: transporte (DPoP + credenciales),
 * redirección a login ante un 401 de sesión y reloj de inactividad
 * sincronizado entre pestañas mientras haya sesión.
 */
export default defineNuxtPlugin(async (nuxtApp) => {
  const config = useRuntimeConfig().public.leo
  const idleState = useState('leo-idle', () => ({ warning: false, deadline: 0 }))
  const sessionState = useState<{ status: string, me: { session: { idle_timeout_seconds: number } } | null }>(
    'leo-session',
    () => ({ status: 'unknown', me: null })
  )

  const store = typeof indexedDB === 'undefined' ? memoryDpopKeyStore() : indexedDbDpopKeyStore()
  const signer = await createDpopSigner(store)

  // Una sola redirección aunque lleguen varios 401; con tope contra bucles de login.
  const goToLogin = createLoginRedirector({
    skip: () => {
      const path = useRouter().currentRoute.value.path
      return path === config.loginPath || (transport.kind === 'bff' && path === config.callbackPath)
    },
    currentPath: () => useRouter().currentRoute.value.fullPath,
    login: (returnTo, reason) => transport.login(returnTo, reason),
    navigate: async (location) => {
      await nuxtApp.runWithContext(() => navigateTo(location.url, { external: location.external, replace: true }))
    },
    guard: loginLoopGuard,
    onBlocked: () => showError(createError({ statusCode: 401, statusMessage: LOGIN_LOOP_MESSAGE, fatal: true })),
    onError: err => showError(createError({ statusCode: 503, statusMessage: leoErrorMessage(err), fatal: true }))
  })

  const redirectToLogin = (reason?: string) => {
    sessionState.value = { status: 'anonymous', me: null }
    return nuxtApp.runWithContext(() => goToLogin(reason))
  }

  if (!config.apiBase) throw new Error('Falta NUXT_PUBLIC_LEO_API_BASE (configuración de leo-client).')
  const onUnauthorized = () => {
    stopTracker()
    void redirectToLogin('expired')
  }

  // 403 `forbidden`: refresca permisos; solo navega si la llamada lo pidió.
  const onForbidden = createForbiddenHandler({
    refresh: () => nuxtApp.runWithContext(() => useLeoSession().ensure(true)),
    goToForbiddenPage: () => void nuxtApp.runWithContext(() =>
      navigateTo({ path: '/leo/forbidden', query: { from: useRouter().currentRoute.value.fullPath } }, { replace: true }))
  })

  const transport: LeoTransport = config.transport === 'bff'
    ? createLeoBffTransport({
        apiBase: config.apiBase,
        publicUrl: config.publicUrl,
        authPath: config.authPath,
        idleTimeoutSeconds: config.idleTimeoutSeconds,
        signer,
        onUnauthorized,
        onForbidden: (_err, mode) => onForbidden(mode)
      })
    : createLeoDirectTransport({
        apiBase: config.apiBase,
        publicUrl: config.publicUrl,
        loginPath: config.loginPath,
        signer,
        onUnauthorized,
        onForbidden: (_err, mode) => onForbidden(mode)
      })

  // ── inactividad ───────────────────────────────────────────────────────
  const channel = broadcastIdleChannel()
  let tracker: IdleTracker | null = null

  const onActivity = () => tracker?.activity()
  const onVisibility = () => {
    if (document.visibilityState !== 'visible') return
    tracker?.check()
    tracker?.activity()
  }

  function stopTracker() {
    tracker?.stop()
    tracker = null
    idleState.value = { warning: false, deadline: 0 }
    for (const event of ACTIVITY_EVENTS) window.removeEventListener(event, onActivity, { capture: true })
    document.removeEventListener('visibilitychange', onVisibility)
  }

  function startTracker(timeoutSeconds: number) {
    stopTracker()
    tracker = createIdleTracker({
      timeoutMs: timeoutSeconds * 1000,
      warnBeforeMs: Math.min(config.idleWarningSeconds * 1000, timeoutSeconds * 500),
      heartbeatIntervalMs: config.heartbeatIntervalSeconds * 1000,
      channel,
      heartbeat: () => transport.heartbeat(),
      onWarn: deadline => { idleState.value = { warning: true, deadline } },
      onActive: () => { idleState.value = { warning: false, deadline: 0 } },
      onExpire: async () => {
        stopTracker()
        await transport.logout().catch(() => {})
        await redirectToLogin('idle')
      },
      onRemoteLogout: (reason: IdleLogoutReason) => {
        stopTracker()
        void redirectToLogin(reason === 'idle' ? 'idle' : undefined)
      }
    })
    for (const event of ACTIVITY_EVENTS) window.addEventListener(event, onActivity, { capture: true, passive: true })
    document.addEventListener('visibilitychange', onVisibility)
    tracker.start()
  }

  watch(
    () => sessionState.value?.status === 'authenticated' ? sessionState.value.me?.session.idle_timeout_seconds ?? 0 : 0,
    (timeout) => {
      if (timeout > 0) startTracker(timeout)
      else stopTracker()
    },
    { immediate: true }
  )

  const idle = {
    stayConnected: () => tracker?.stayConnected(),
    broadcastLogout: (reason: IdleLogoutReason) => {
      if (tracker) tracker.broadcastLogout(reason)
      else channel?.post({ type: 'logout', reason })
      stopTracker()
    }
  }

  return { provide: { leo: { transport, idle } } }
})
