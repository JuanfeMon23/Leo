const MAX_UNKNOWN = 60

/** Navegadores en orden de precedencia (Edge, Opera y Chrome comparten «Chrome/»). */
const BROWSERS: ReadonlyArray<readonly [string, RegExp]> = [
  ['Edge', /\bEdg(?:e|A|iOS)?\/(\d+)/],
  ['Opera', /\bOPR\/(\d+)/],
  ['Firefox', /\b(?:Firefox|FxiOS)\/(\d+)/],
  ['Chrome', /\b(?:Chrome|CriOS)\/(\d+)/],
  ['Safari', /\bVersion\/(\d+)[\d.]*.*\bSafari\//]
]

const SYSTEMS: ReadonlyArray<readonly [string, RegExp]> = [
  ['Android', /Android/],
  ['iOS', /iPhone|iPad|iPod/],
  ['Windows', /Windows/],
  ['macOS', /Macintosh|Mac OS X/],
  ['Linux', /Linux|X11/]
]

/**
 * «Chrome 141 en Windows» a partir del user-agent. Si no es un navegador
 * conocido (cliente HTTP, script) devuelve el texto recortado; sin dato,
 * «Desconocido».
 */
export function summarizeUserAgent(userAgent: string | null | undefined): string {
  const trimmedAgent = userAgent?.trim()
  if (!trimmedAgent) return 'Desconocido'
  const browser = BROWSERS.map(([name, pattern]) => [name, pattern.exec(trimmedAgent)?.[1]] as const).find(([, version]) => version)
  if (!browser) return trimmedAgent.length > MAX_UNKNOWN ? `${trimmedAgent.slice(0, MAX_UNKNOWN - 1)}…` : trimmedAgent
  const system = SYSTEMS.find(([, pattern]) => pattern.test(trimmedAgent))?.[0]
  return system ? `${browser[0]} ${browser[1]} en ${system}` : `${browser[0]} ${browser[1]}`
}
