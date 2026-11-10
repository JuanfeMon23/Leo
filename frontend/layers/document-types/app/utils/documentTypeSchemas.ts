import { z } from 'zod'
import { zRequiredText } from '#andromeda/utils/zodFields'

const zSortOrder = z.preprocess(
  value => (typeof value === 'string' ? (value.trim() === '' ? undefined : Number(value)) : value),
  z.number({ required_error: 'El orden es obligatorio.', invalid_type_error: 'El orden debe ser un número entero.' })
    .int('El orden debe ser un número entero.')
    .min(0, 'El orden no puede ser negativo.')
)

export const documentTypeCreateSchema = z.object({
  // El código se guarda en mayúsculas; el backend valida su forma exacta.
  code: z.preprocess(
    value => (typeof value === 'string' ? value.trim().toUpperCase() : value),
    zRequiredText('El código es obligatorio.', 16)
  ),
  name: zRequiredText('El nombre es obligatorio.', 100),
  sort_order: zSortOrder
})

export type DocumentTypeCreateInput = z.input<typeof documentTypeCreateSchema>
