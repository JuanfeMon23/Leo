import { hasPermission } from '../lib/permissions'
import type { LeoTagMode } from '../lib/permissions'
import type { LeoMe } from '../lib/types'

export type LeoSessionStatus = 'unknown' | 'authenticated' | 'anonymous'

interface LeoSessionState {
  status: LeoSessionStatus
  me: LeoMe | null
}

let loading: Promise<void> | null = null

/**
 * Sesión de Leo en el navegador: usuario, permisos (tags) y apps accesibles.
 * La fuente es `/auth/me` (o el login); nunca hay tokens aquí: la cookie es
 * HttpOnly y la llave DPoP no es exportable.
 */
export function useLeoSession() {
  const state = useState<LeoSessionState>('leo-session', () => ({ status: 'unknown', me: null }))
  const { $leo } = useNuxtApp()

  const me = computed(() => state.value.me)
  const user = computed(() => state.value.me?.user ?? null)
  const permissions = computed(() => state.value.me?.permissions ?? [])
  const applications = computed(() => state.value.me?.applications ?? [])
  const isAuthenticated = computed(() => state.value.status === 'authenticated')
  const permissionSet = computed(() => new Set(permissions.value))

  function setMe(value: LeoMe) {
    state.value = { status: 'authenticated', me: value }
  }

  function clear() {
    state.value = { status: 'anonymous', me: null }
  }

  /** Carga `/auth/me` una sola vez (o de nuevo con `force`). */
  async function ensure(force = false) {
    if (!force && state.value.status !== 'unknown') return
    loading ??= $leo.transport.me()
      .then(value => (value ? setMe(value) : clear()))
      .finally(() => { loading = null })
    await loading
  }

  function can(tags: string | readonly string[], mode: LeoTagMode = 'all') {
    return hasPermission(permissionSet.value, tags, mode)
  }

  /** Lleva al login conservando la ruta actual (o `returnTo`). */
  async function redirectToLogin(reason?: string, returnTo?: string) {
    const target = returnTo ?? useRouter().currentRoute.value.fullPath
    const location = await $leo.transport.login(target, reason)
    await navigateTo(location.url, { external: location.external, replace: true })
  }

  /** Cierra la sesión en el servidor y en todas las pestañas, y va al login. */
  async function logout() {
    $leo.idle.broadcastLogout('manual')
    try {
      await $leo.transport.logout()
    } finally {
      clear()
      await redirectToLogin(undefined, '/')
    }
  }

  return { state, me, user, permissions, applications, isAuthenticated, setMe, clear, ensure, can, redirectToLogin, logout }
}
