import { zRequiredText } from '#andromeda/utils/zodFields'

/** Segmento kebab-case (mismo patrón que el backend: `SLUG_PATTERN`). */
export const SLUG_REGEX = /^[a-z0-9]+(-[a-z0-9]+)*$/

export const SLUG_MESSAGE = 'Usa minúsculas, números y guiones (kebab-case), por ejemplo «mi-app».'

/** Campo zod de slug/verbo kebab-case, máx. 64 (igual que `Slug` del backend). */
export function zSlug(requiredMessage: string) {
  return zRequiredText(requiredMessage, 64).regex(SLUG_REGEX, SLUG_MESSAGE)
}
