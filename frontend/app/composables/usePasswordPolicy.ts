import type { PasswordPolicy } from '#andromeda/utils/passwordPolicy'

/** Vigencia del valor en memoria; evita pedir la política en cada modal o formulario. */
const CACHE_TTL_MS = 30_000

/** Política estricta que se usa mientras no llega la del servidor o si falla la carga. */
export const DEFAULT_PASSWORD_POLICY: PasswordPolicy = {
  min_length: 12,
  max_length: 128,
  require_lowercase: true,
  require_uppercase: true,
  require_digit: true,
  require_symbol: true
}

const BOOLEAN_KEYS = ['require_lowercase', 'require_uppercase', 'require_digit', 'require_symbol'] as const

function isPasswordPolicy(value: unknown): value is PasswordPolicy {
  const v = value as Record<string, unknown> | null
  return !!v
    && Number.isInteger(v.min_length) && Number.isInteger(v.max_length)
    && BOOLEAN_KEYS.every(key => typeof v[key] === 'boolean')
}

let cached: { policy: PasswordPolicy, at: number } | null = null
let inFlight: Promise<PasswordPolicy | null> | null = null

/** Descarta el valor en memoria (cierre de sesión y pruebas). */
export function clearPasswordPolicyCache() {
  cached = null
  inFlight = null
}

/**
 * Política de contraseña vigente en el servidor (`GET /auth/password-policy`,
 * pública), con caché en memoria ~30 s. Hasta que llega, o si la carga falla
 * o devuelve algo inválido, `policy` es `DEFAULT_PASSWORD_POLICY` (estricta);
 * el backend sigue siendo la autoridad. Reactiva: los formularios y
 * `UiPasswordRequirements` se actualizan cuando llega.
 */
export function usePasswordPolicy() {
  const api = useLeoApi()
  const fresh = () => (cached && Date.now() - cached.at < CACHE_TTL_MS ? cached.policy : null)
  const policy = ref<PasswordPolicy>(fresh() ?? DEFAULT_PASSWORD_POLICY)

  async function fetchPolicy(): Promise<PasswordPolicy | null> {
    try {
      const value = await api<unknown>('/auth/password-policy', { skipSessionHandling: true })
      if (!isPasswordPolicy(value)) return null
      cached = { policy: value, at: Date.now() }
      return value
    } catch {
      return null // sin red o error del servidor: se queda con la política estricta
    }
  }

  async function load(): Promise<void> {
    const hit = fresh()
    if (hit) {
      policy.value = hit
      return
    }
    inFlight ??= fetchPolicy().finally(() => { inFlight = null })
    const loaded = await inFlight
    if (loaded) policy.value = loaded
  }

  void load()

  return { policy, load }
}
