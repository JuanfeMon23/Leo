import { z } from 'zod'
import { zOptionalText, zRequiredId, zRequiredText } from '#andromeda/utils/zodFields'
import { zSlug } from '../../../../app/utils/slug'

export const roleCreateSchema = z.object({
  application_id: zRequiredId('Elige la aplicación del rol.'),
  slug: zSlug('El identificador es obligatorio.'),
  name: zRequiredText('El nombre es obligatorio.', 128),
  description: zOptionalText(2000)
})

/** La aplicación y el slug son inmutables: no forman parte del formulario de edición. */
export const roleEditSchema = roleCreateSchema.omit({ application_id: true, slug: true })

export type RoleCreateInput = z.input<typeof roleCreateSchema>
export type RoleEditInput = z.input<typeof roleEditSchema>
