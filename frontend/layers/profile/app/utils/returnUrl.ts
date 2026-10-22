/** App del ecosistema a la que se puede volver (subconjunto de `me.applications`). */
export interface ProfileReturnApp {
  name: string
  base_url: string
}

export interface ProfileReturnTarget {
  url: string
  app: ProfileReturnApp
}

function originOf(value: string): string | null {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null
  } catch {
    return null
  }
}

/**
 * Destino de `?return=`: SOLO una URL absoluta http(s) cuyo ORIGEN coincide con
 * el `base_url` de alguna app a la que la persona tiene acceso. Evita
 * redirecciones abiertas (`javascript:`, otro origen, relativas, `//evil.com`,
 * `https://app@evil.com`). Devuelve la URL normalizada por el parser; `null`
 * si no es válida (no se muestra enlace).
 */
export function safeReturnUrl(
  returnParam: unknown,
  applications: readonly ProfileReturnApp[]
): ProfileReturnTarget | null {
  if (typeof returnParam !== 'string' || !returnParam.trim()) return null
  let parsed: URL
  try {
    parsed = new URL(returnParam.trim())
  } catch {
    return null // relativa, `//evil.com`, vacía o malformada
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null
  if (parsed.username || parsed.password) return null
  const app = applications.find(a => originOf(a.base_url) === parsed.origin)
  return app ? { url: parsed.href, app } : null
}
