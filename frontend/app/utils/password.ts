export interface PasswordRequirement {
  id: 'length' | 'lower' | 'upper' | 'digit' | 'symbol' | 'personal'
  label: string
  met: boolean
}

/** Misma política que el backend (`password_weaknesses` en core/security/passwords.py). */
export const PASSWORD_MIN = 12
export const PASSWORD_MAX = 128

export interface PasswordContext {
  username?: string
  email?: string
}

/**
 * Requisitos de la contraseña y si se cumplen (para el indicador en vivo y
 * para validar). El backend sigue siendo la autoridad; aquí solo se anticipa.
 */
export function passwordRequirements(password: string, ctx: PasswordContext = {}): PasswordRequirement[] {
  const length = [...password].length
  const lowered = password.toLowerCase()
  const local = ctx.email ? ctx.email.split('@', 1)[0] : undefined
  const personal = [ctx.username, local].some(p => p && p.length >= 3 && lowered.includes(p.toLowerCase()))
  return [
    { id: 'length', label: `Entre ${PASSWORD_MIN} y ${PASSWORD_MAX} caracteres`, met: length >= PASSWORD_MIN && length <= PASSWORD_MAX },
    { id: 'lower', label: 'Una letra minúscula', met: /\p{Ll}/u.test(password) },
    { id: 'upper', label: 'Una letra mayúscula', met: /\p{Lu}/u.test(password) },
    { id: 'digit', label: 'Un número', met: /\p{Nd}/u.test(password) },
    { id: 'symbol', label: 'Un símbolo (por ejemplo ! ? - _ . @ #)', met: /[^\p{L}\p{N}]/u.test(password) },
    { id: 'personal', label: 'No contiene el usuario ni la parte del correo antes de la @', met: !personal }
  ]
}

/** Etiquetas de los requisitos que faltan; `[]` si la contraseña es fuerte. */
export function passwordProblems(password: string, ctx: PasswordContext = {}): string[] {
  return passwordRequirements(password, ctx).filter(r => !r.met).map(r => r.label)
}
