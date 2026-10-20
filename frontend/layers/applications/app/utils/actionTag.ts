import { SLUG_REGEX } from '../../../../app/utils/slug'

/** Slug de la app que mantiene la semilla: la UI la muestra en solo lectura. */
export const PROTECTED_APP_SLUG = 'leo'

export function isProtectedApp(slug: string): boolean {
  return slug === PROTECTED_APP_SLUG
}

/**
 * Vista previa en vivo del tag que armará el backend (`<app>.<modulo>.<verbo>`).
 * `complete` es true solo con un verbo kebab-case válido. El backend es quien
 * lo arma de verdad: esto solo muestra al usuario qué va a quedar registrado.
 */
export function previewActionTag(appSlug: string, moduleSlug: string, verb: string): { text: string, complete: boolean } {
  const trimmed = verb.trim()
  return {
    text: `${appSlug}.${moduleSlug}.${trimmed || '‹verbo›'}`,
    complete: SLUG_REGEX.test(trimmed)
  }
}
