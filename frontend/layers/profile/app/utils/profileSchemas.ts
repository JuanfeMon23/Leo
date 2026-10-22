import { z } from 'zod'
import { zRequiredText } from '#andromeda/utils/zodFields'
import { zEmail } from '../../../../app/utils/email'
import type { PasswordContext } from '../../../../app/utils/password'
import { passwordProblems } from '../../../../app/utils/password'

/** Datos personales editables por la propia persona (el usuario y el documento no). */
export const profileSchema = z.object({
  first_name: zRequiredText('Los nombres son obligatorios.', 100),
  last_name: zRequiredText('Los apellidos son obligatorios.', 100),
  email: zEmail
})

export type ProfileInput = z.input<typeof profileSchema>

const requiredPassword = (message: string) =>
  z.string({ required_error: message }).min(1, message)

/**
 * Cambio de contraseña propio. La política es la del backend (`password.ts`),
 * con el usuario y el correo ACTUALES (`ctx` puede ser una función que los lea al validar); además debe ser distinta de la actual y
 * coincidir con la confirmación. El backend sigue siendo la autoridad.
 */
export function passwordChangeSchema(ctx: PasswordContext | (() => PasswordContext)) {
  return z.object({
    current_password: requiredPassword('Ingresa tu contraseña actual.'),
    new_password: requiredPassword('Ingresa la contraseña nueva.'),
    confirm_password: requiredPassword('Confirma la contraseña nueva.')
  }).superRefine((v, issue) => {
    if (v.new_password) {
      const problems = passwordProblems(v.new_password, typeof ctx === 'function' ? ctx() : ctx)
      if (problems.length) {
        const lower = problems.map(p => p.charAt(0).toLowerCase() + p.slice(1))
        issue.addIssue({ code: 'custom', path: ['new_password'], message: `Falta: ${lower.join('; ')}.` })
      } else if (v.new_password === v.current_password) {
        issue.addIssue({ code: 'custom', path: ['new_password'], message: 'La contraseña nueva debe ser distinta de la actual.' })
      }
    }
    if (v.confirm_password && v.new_password !== v.confirm_password) {
      issue.addIssue({ code: 'custom', path: ['confirm_password'], message: 'Las contraseñas no coinciden.' })
    }
  })
}
