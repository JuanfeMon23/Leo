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
  const ua = userAgent?.trim()
  if (!ua) return 'Desconocido'
  const browser = BROWSERS.map(([name, re]) => [name, re.exec(ua)?.[1]] as const).find(([, v]) => v)
  if (!browser) return ua.length > MAX_UNKNOWN ? `${ua.slice(0, MAX_UNKNOWN - 1)}…` : ua
  const system = SYSTEMS.find(([, re]) => re.test(ua))?.[0]
  return system ? `${browser[0]} ${browser[1]} en ${system}` : `${browser[0]} ${browser[1]}`
}
