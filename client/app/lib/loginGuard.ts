/**
 * Corta bucles login → callback → 401 (p. ej. `invalid_dpop_proof` sistemático
 * con el SSO vigente): cuenta las redirecciones a login en `sessionStorage`
 * dentro de una ventana; al excederla no se redirige y se muestra el error.
 */
export const LOGIN_LOOP_MESSAGE = 'No pudimos iniciar tu sesión. Cierra la pestaña e inténtalo de nuevo.'

const KEY = 'leo:login-attempts'

export interface LoginLoopGuard {
  /** Registra una redirección a login; `false` si excede el máximo de la ventana (no registra). */
  attempt(): boolean
  /** Sesión exitosa (`me()` ok): reinicia el contador. */
  reset(): void
}

export interface LoginLoopGuardOptions {
  windowMs?: number
  /** Redirecciones permitidas por ventana. */
  max?: number
  now?: () => number
  storage?: () => Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null
}

function defaultStorage() {
  try {
    return globalThis.sessionStorage ?? null
  } catch {
    return null
  }
}

export function createLoginLoopGuard(options: LoginLoopGuardOptions = {}): LoginLoopGuard {
  const windowMs = options.windowMs ?? 30_000
  const max = options.max ?? 2
  const now = options.now ?? Date.now
  const storage = options.storage ?? defaultStorage
  let memory: number[] = []

  function read(): number[] {
    try {
      const raw = storage()?.getItem(KEY)
      if (raw == null) return memory
      const parsed: unknown = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed.filter((n): n is number => typeof n === 'number') : []
    } catch {
      return memory
    }
  }

  function write(values: number[]) {
    memory = values
    try {
      storage()?.setItem(KEY, JSON.stringify(values))
    } catch { /* sin almacenamiento: queda en memoria */ }
  }

  return {
    attempt() {
      const t = now()
      const recent = read().filter(at => t - at < windowMs)
      if (recent.length >= max) {
        write(recent)
        return false
      }
      write([...recent, t])
      return true
    },
    reset() {
      memory = []
      try {
        storage()?.removeItem(KEY)
      } catch { /* idem */ }
    }
  }
}

/** Instancia de la app (sessionStorage del navegador). */
export const loginLoopGuard = createLoginLoopGuard()
