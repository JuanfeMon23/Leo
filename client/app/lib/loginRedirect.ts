import type { LoginLoopGuard } from './loginGuard'
import type { LeoLoginLocation } from './transport'

export interface LoginRedirectorOptions {
  /** Ya en login (direct) o cerrando el login (bff): no pedir otro. */
  skip(): boolean
  /** Ruta actual (el `returnTo` del primer aviso). */
  currentPath(): string
  login(returnTo: string, reason?: string): Promise<LeoLoginLocation>
  navigate(location: LeoLoginLocation): Promise<unknown>
  guard: LoginLoopGuard
  /** Se excedió el máximo de redirecciones: mostrar el error, no redirigir. */
  onBlocked(): void
  /** No se pudo obtener/navegar al login. */
  onError(err: unknown): void
}

/**
 * Redirección a login deduplicada: varios 401 simultáneos (o logout remoto +
 * 401) producen UNA sola redirección, con el `returnTo` del primero. Tras una
 * redirección externa no se vuelve a pedir (la página se está descargando).
 */
export function createLoginRedirector(options: LoginRedirectorOptions): (reason?: string) => Promise<void> {
  let inFlight: Promise<void> | null = null

  return (reason) => {
    if (inFlight) return inFlight
    if (options.skip()) return Promise.resolve()
    if (!options.guard.attempt()) {
      options.onBlocked()
      return Promise.resolve()
    }
    const returnTo = options.currentPath()
    inFlight = (async () => {
      let keep = false
      try {
        const location = await options.login(returnTo, reason)
        await options.navigate(location)
        keep = location.external
      } catch (err) {
        options.onError(err)
      } finally {
        if (!keep) inFlight = null
      }
    })()
    return inFlight
  }
}
