import { z } from 'zod'
import { zPassword } from '#andromeda/utils/passwordPolicy'
import type { PasswordPolicy } from '#andromeda/utils/passwordPolicy'

/**
 * Campo de contraseña nueva cuya política se lee en cada validación (`z.lazy`):
 * el formulario se crea antes de que llegue la política del servidor
 * (`usePasswordPolicy`) y debe validar con la vigente en ese momento.
 */
export function zLazyPassword(policy: () => PasswordPolicy, messages?: Parameters<typeof zPassword>[1]) {
  return z.lazy(() => zPassword(policy(), messages))
}
