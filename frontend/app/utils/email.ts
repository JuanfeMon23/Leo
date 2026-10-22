import { z } from 'zod'

/** Misma forma mínima que el backend (modules/users/models.py). */
export const EMAIL_REGEX = /^[^@\s]+@[^@\s]+$/

/** Correo obligatorio: sin espacios en los extremos, máx. 254, forma `a@b`. */
export const zEmail = z.string({ required_error: 'El correo es obligatorio.' })
  .trim()
  .min(1, 'El correo es obligatorio.')
  .max(254, 'Máximo 254 caracteres.')
  .regex(EMAIL_REGEX, 'Ingresa un correo electrónico válido.')
