import { z } from 'zod'
import { zOptionalText, zRequiredText } from '#andromeda/utils/zodFields'
import { zSlug } from '../../../../app/utils/slug'

export const MAX_REDIRECT_URIS = 20

/** Por qué una URL no vale (o `null` si vale): http(s) absoluta, sin fragmento. */
function httpUrlProblem(value: string): string | null {
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return 'debe ser una URL absoluta http o https.'
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return 'debe ser una URL absoluta http o https.'
  if (value.includes('#')) return 'no puede tener fragmento (#).'
  return null
}

const baseUrlField = zRequiredText('La URL base es obligatoria.', 512).superRefine((value, ctx) => {
  const problem = httpUrlProblem(value)
  if (problem) ctx.addIssue({ code: z.ZodIssueCode.custom, message: `La URL base ${problem}` })
})

/** Una redirect URI por línea (textarea) → lista sin vacíos ni repetidos. */
const redirectUrisField = z
  .string()
  .optional()
  .transform((value, ctx) => {
    const lines = (value ?? '').split(/\r?\n/)
    const uris: string[] = []
    let failed = false
    lines.forEach((line, index) => {
      const uri = line.trim()
      if (!uri) return
      const problem = httpUrlProblem(uri)
      if (problem) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: `Línea ${index + 1}: ${problem}` })
        failed = true
        return
      }
      if (!uris.includes(uri)) uris.push(uri)
    })
    if (!failed && uris.length > MAX_REDIRECT_URIS) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: `Máximo ${MAX_REDIRECT_URIS} redirect URIs.` })
    }
    return failed ? z.NEVER : uris
  })

const nameField = zRequiredText('El nombre es obligatorio.', 128)
const descriptionField = zOptionalText(2000)

export const applicationCreateSchema = z.object({
  slug: zSlug('El identificador es obligatorio.'),
  name: nameField,
  description: descriptionField,
  base_url: baseUrlField,
  redirect_uris: redirectUrisField
})

/** El slug (= client_id) no se edita: no forma parte del formulario de edición. */
export const applicationEditSchema = applicationCreateSchema.omit({ slug: true })

export const moduleCreateSchema = z.object({
  slug: zSlug('El identificador es obligatorio.'),
  name: nameField,
  description: descriptionField
})

export const moduleEditSchema = moduleCreateSchema.omit({ slug: true })

/** Nombre legible del permiso (1..120, como `ActionName` del backend). */
const actionNameField = zRequiredText('El nombre del permiso es obligatorio.', 120)

export const actionCreateSchema = z.object({
  verb: zSlug('El verbo es obligatorio.'),
  name: actionNameField,
  description: descriptionField
})

export const actionEditSchema = actionCreateSchema.omit({ verb: true })

export type ApplicationCreateInput = z.input<typeof applicationCreateSchema>
export type ApplicationEditInput = z.input<typeof applicationEditSchema>
export type ModuleCreateInput = z.input<typeof moduleCreateSchema>
export type ModuleEditInput = z.input<typeof moduleEditSchema>
export type ActionCreateInput = z.input<typeof actionCreateSchema>
export type ActionEditInput = z.input<typeof actionEditSchema>

/** Lista de redirect URIs → texto del textarea (una por línea). */
export function redirectUrisToText(uris: readonly string[]): string {
  return uris.join('\n')
}
