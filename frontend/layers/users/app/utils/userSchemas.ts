import { z } from 'zod'
import { zRequiredEnum, zRequiredText } from '#andromeda/utils/zodFields'
import { zEmail } from '../../../../app/utils/email'
import { USERS_DOCUMENT_TYPES } from '../types/users'
import type { PasswordPolicy } from '#andromeda/utils/passwordPolicy'
import { zLazyPassword } from '../../../../app/utils/lazyPassword'

// Mismos patrones que el backend (modules/users/models.py).
export const USERS_USERNAME_REGEX = /^[a-z0-9]([a-z0-9._-]{1,62})[a-z0-9]$/
export const USERS_DOCUMENT_NUMBER_REGEX = /^[0-9A-Z]+(-[0-9A-Z]+)*$/

export const USERS_DOCUMENT_LABELS: Record<typeof USERS_DOCUMENT_TYPES[number], string> = {
  CC: 'Cédula de ciudadanía',
  CE: 'Cédula de extranjería',
  TI: 'Tarjeta de identidad',
  RC: 'Registro civil',
  PA: 'Pasaporte',
  NIT: 'NIT',
  PEP: 'Permiso especial de permanencia',
  PPT: 'Permiso por protección temporal'
}

const zUsername = z.preprocess(
  v => (typeof v === 'string' ? v.trim().toLowerCase() : v),
  z.string({ required_error: 'El usuario es obligatorio.' })
    .min(1, 'El usuario es obligatorio.')
    .superRefine((v, ctx) => {
      if (v.includes('@')) ctx.addIssue({ code: 'custom', message: 'El usuario no puede contener «@».' })
      else if (v.length < 3 || v.length > 64) ctx.addIssue({ code: 'custom', message: 'Debe tener entre 3 y 64 caracteres.' })
      else if (!USERS_USERNAME_REGEX.test(v)) ctx.addIssue({ code: 'custom', message: 'Usa minúsculas, números y . _ - (sin empezar ni terminar con símbolo).' })
    })
)

const zDocumentNumber = z.preprocess(
  v => (typeof v === 'string' ? v.trim().toUpperCase() : v),
  z.string({ required_error: 'El número de documento es obligatorio.' })
    .min(1, 'El número de documento es obligatorio.')
    .max(32, 'Máximo 32 caracteres.')
    .regex(USERS_DOCUMENT_NUMBER_REGEX, 'Solo letras y números, sin puntos ni espacios (se admiten guiones internos).')
)

const personFields = {
  email: zEmail,
  document_type: zRequiredEnum(USERS_DOCUMENT_TYPES, 'Elige el tipo de documento.'),
  document_number: zDocumentNumber,
  first_name: zRequiredText('Los nombres son obligatorios.', 100),
  last_name: zRequiredText('Los apellidos son obligatorios.', 100)
}

/** Alta de usuario; la política de contraseña se lee en cada validación (la del servidor). */
export function userCreateSchema(policy: () => PasswordPolicy) {
  return z.object({ username: zUsername, ...personFields, password: zLazyPassword(policy, { required: 'La contraseña es obligatoria.' }) })
}

/** El usuario (login) es inmutable y la contraseña se cambia aparte: no forman parte de la edición. */
export const userEditSchema = z.object(personFields)

/** Reseteo de contraseña por un administrador: misma política que el alta. */
export function passwordResetSchema(policy: () => PasswordPolicy) {
  return z.object({ password: zLazyPassword(policy, { required: 'La contraseña es obligatoria.' }) })
}

export type UserCreateInput = z.input<ReturnType<typeof userCreateSchema>>
export type UserEditInput = z.input<typeof userEditSchema>
