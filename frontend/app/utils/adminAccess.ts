/**
 * Acceso al panel administrativo de Leo: toda ruta exige al menos un permiso `leo.*`,
 * salvo las públicas (login, authorize, callback: `leo.public`), el perfil propio, las
 * páginas de error de leo-client y la propia página «Sin acceso». Lista cerrada: una
 * ruta nueva es administrativa por defecto.
 */
export const NO_ACCESS_PATH = '/sin-acceso'

const SELF_SERVICE = ['/profile', NO_ACCESS_PATH, '/leo']

/** ¿La ruta es administrativa (exige algún `leo.*`)? */
export function isAdminRoute(path: string): boolean {
  return !SELF_SERVICE.some(base => path === base || path.startsWith(`${base}/`))
}

/** ¿Tiene al menos un permiso del panel (`leo.*`)? */
export function hasAdminAccess(permissions: readonly string[] | null | undefined): boolean {
  return !!permissions?.some(tag => tag.startsWith('leo.'))
}
