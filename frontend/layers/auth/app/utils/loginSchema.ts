import { z } from 'zod'
import { zRequiredText } from '#andromeda/utils/zodFields'

/** Formulario de login. Máximos = los del backend (`LoginRequest`). */
export const loginSchema = z.object({
  login: zRequiredText('Ingresa tu usuario o correo electrónico.', 254),
  // La contraseña no se recorta: los espacios pueden ser parte de ella.
  password: z
    .string({ required_error: 'Ingresa tu contraseña.', invalid_type_error: 'Ingresa tu contraseña.' })
    .min(1, 'Ingresa tu contraseña.')
    .max(1024, 'Máximo 1024 caracteres.')
})

export type LoginForm = z.input<typeof loginSchema>
export type LoginPayload = z.output<typeof loginSchema>
