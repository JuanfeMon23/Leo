/**
 * Destino de vuelta tras el login (`?redirect=`): solo rutas internas del
 * mismo origen. Evita open redirects (`//evil`, `/\evil`, `https://…`,
 * `javascript:`), también si vienen codificadas.
 */
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/

function isInternalPath(path: string): boolean {
  return path.startsWith('/') && !path.startsWith('//') && !path.startsWith('/\\') && !CONTROL_CHARS.test(path)
}

export function safeReturnTo(value: unknown, fallback = '/'): string {
  if (typeof value !== 'string') return fallback
  let decoded: string
  try {
    decoded = decodeURIComponent(value)
  } catch {
    return fallback
  }
  return isInternalPath(value) && isInternalPath(decoded) ? value : fallback
}
