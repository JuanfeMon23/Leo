import { createDpopSigner, indexedDbDpopKeyStore, memoryDpopKeyStore } from '../lib/dpop'
import { broadcastIdleChannel, createIdleTracker } from '../lib/idleTracker'
import type { IdleLogoutReason, IdleTracker } from '../lib/idleTracker'
import { leoErrorMessage } from '../lib/errors'
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

  const goToLogin = (reason?: string) =>
    nuxtApp.runWithContext(async () => {
      sessionState.value = { status: 'anonymous', me: null }
      const route = useRouter().currentRoute.value
      // Ya en login (direct) o cerrando el login (bff): no pedir otro.
      if (route.path === config.loginPath || (transport.kind === 'bff' && route.path === config.callbackPath)) return
      try {
        const location = await transport.login(route.fullPath, reason)
        return await navigateTo(location.url, { external: location.external, replace: true })
      } catch (err) {
        showError(createError({ statusCode: 503, statusMessage: leoErrorMessage(err), fatal: true }))
      }
    })

  if (!config.apiBase) throw new Error('Falta NUXT_PUBLIC_LEO_API_BASE (configuración de leo-client).')
  const onUnauthorized = () => {
    stopTracker()
    void goToLogin('expired')
  }
  const transport: LeoTransport = config.transport === 'bff'
    ? createLeoBffTransport({
        apiBase: config.apiBase,
        publicUrl: config.publicUrl,
        authPath: config.authPath,
        idleTimeoutSeconds: config.idleTimeoutSeconds,
        signer,
        onUnauthorized
      })
    : createLeoDirectTransport({
        apiBase: config.apiBase,
        publicUrl: config.publicUrl,
        loginPath: config.loginPath,
        signer,
        onUnauthorized
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
        await goToLogin('idle')
      },
      onRemoteLogout: (reason: IdleLogoutReason) => {
        stopTracker()
        void goToLogin(reason === 'idle' ? 'idle' : undefined)
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
