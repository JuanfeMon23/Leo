import { z } from 'zod'
import { zRequiredText, zRequiredWhenChanged } from '#andromeda/utils/zodFields'
import type { PasswordPolicy } from '#andromeda/utils/passwordPolicy'
import { zEmail } from '../../../../app/utils/email'
import { zLazyPassword } from '../../../../app/utils/lazyPassword'

/** Datos personales editables por la propia persona (el usuario y el documento no). */
export const profileSchema = z.object({
  first_name: zRequiredText('Los nombres son obligatorios.', 100),
  last_name: zRequiredText('Los apellidos son obligatorios.', 100),
  email: zEmail
})

export type ProfileInput = z.input<typeof profileSchema>

/**
 * Formulario de datos personales: `profileSchema` + «Contraseña actual», obligatoria
 * solo si el correo cambió respecto al actual (`currentEmail` se lee al validar).
 * El backend sigue siendo la autoridad (`current_password_required`).
 */
export function profileFormSchema(currentEmail: () => string) {
  return zRequiredWhenChanged(profileSchema.extend({ current_password: z.string().optional() }), {
    watch: 'email',
    require: 'current_password',
    current: currentEmail,
    message: 'Ingresa tu contraseña actual para cambiar el correo.',
    applies: email => email !== ''
  })
}

const requiredPassword = (message: string) =>
  z.string({ required_error: message }).min(1, message)

/**
 * Cambio de contraseña propio. La política es la del servidor (`policy` se lee al
 * validar); además debe ser distinta de la actual y coincidir con la confirmación.
 * El backend sigue siendo la autoridad.
 */
export function passwordChangeSchema(policy: () => PasswordPolicy) {
  return z.object({
    current_password: requiredPassword('Ingresa tu contraseña actual.'),
    new_password: zLazyPassword(policy, { required: 'Ingresa la contraseña nueva.' }),
    confirm_password: requiredPassword('Confirma la contraseña nueva.')
  }).superRefine((v, issue) => {
    if (v.new_password && v.new_password === v.current_password) {
      issue.addIssue({ code: 'custom', path: ['new_password'], message: 'La contraseña nueva debe ser distinta de la actual.' })
    }
    if (v.confirm_password && v.new_password !== v.confirm_password) {
      issue.addIssue({ code: 'custom', path: ['confirm_password'], message: 'Las contraseñas no coinciden.' })
    }
  })
}
