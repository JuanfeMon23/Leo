import type { LeoForbiddenMode } from './transport'

export interface ForbiddenHandlerOptions {
  /** Refresca la sesión (`session.ensure(true)`). */
  refresh(): Promise<unknown>
  /** Navega a `/leo/forbidden` (solo con `onForbidden: 'forbidden-page'`). */
  goToForbiddenPage(): void
}

/**
 * 403 `forbidden`: refresca permisos para que menús y LeoCan reflejen
 * revocaciones. Una sola vez a la vez: los 403 que lleguen (o provoque el
 * propio refresco) mientras se refresca no encadenan otro.
 */
export function createForbiddenHandler(options: ForbiddenHandlerOptions): (mode: LeoForbiddenMode) => void {
  let refreshing = false
  return (mode) => {
    if (mode === 'forbidden-page') options.goToForbiddenPage()
    if (refreshing) return
    refreshing = true
    void options.refresh().catch(() => {}).finally(() => { refreshing = false })
  }
}
