import { describe, expect, it } from 'vitest'
import type { PasswordPolicy } from '#andromeda/utils/passwordPolicy'
import { passwordResetSchema, userCreateSchema, userEditSchema } from './userSchemas'

const STRICT: PasswordPolicy = {
  min_length: 12, max_length: 128, require_lowercase: true, require_uppercase: true, require_digit: true, require_symbol: true
}
let policy = STRICT
const userCreate = userCreateSchema(() => policy)

const valid = {
  username: 'ana.perez',
  email: 'ana@x.co',
  first_name: 'Ana',
  last_name: 'Pérez',
  document_type: 'CC',
  document_number: '1234567',
  password: 'Segura-Clave-2026'
}
const issues = (input: unknown) => {
  const r = userCreate.safeParse(input)
  return r.success ? {} : Object.fromEntries(r.error.issues.map(i => [i.path.join('.'), i.message])) as Record<string, string>
}

describe('userCreateSchema', () => {
  it('acepta datos válidos y normaliza usuario (minúsculas) y documento (mayúsculas)', () => {
    const r = userCreate.parse({ ...valid, username: ' Ana.Perez ', document_number: ' ab-12 ', email: ' ana@x.co ' })
    expect(r).toMatchObject({ username: 'ana.perez', document_number: 'AB-12', email: 'ana@x.co', first_name: 'Ana' })
  })

  it('usuario: 3–64, sin @, formato del backend', () => {
    expect(issues({ ...valid, username: 'ab' }).username).toBeTruthy()
    expect(issues({ ...valid, username: 'a'.repeat(65) }).username).toBeTruthy()
    expect(issues({ ...valid, username: 'ana@x' }).username).toMatch(/@/)
    expect(issues({ ...valid, username: '.ana' }).username).toBeTruthy()
    expect(issues({ ...valid, username: '' }).username).toBeTruthy()
  })

  it('correo con la forma mínima del backend', () => {
    expect(issues({ ...valid, email: 'sin-arroba' }).email).toBeTruthy()
    expect(issues({ ...valid, email: 'a b@x.co' }).email).toBeTruthy()
    expect(issues({ ...valid, email: '' }).email).toBeTruthy()
  })

  it('documento: tipo de la lista y número sin puntos ni espacios', () => {
    expect(issues({ ...valid, document_type: '' }).document_type).toBeTruthy()
    expect(issues({ ...valid, document_type: 'XX' }).document_type).toBeTruthy()
    expect(issues({ ...valid, document_number: '1.234.567' }).document_number).toMatch(/puntos/)
    expect(issues({ ...valid, document_number: '12 34' }).document_number).toBeTruthy()
    expect(issues({ ...valid, document_number: '' }).document_number).toBeTruthy()
    expect(issues({ ...valid, document_number: '1'.repeat(33) }).document_number).toBeTruthy()
  })

  it('nombres obligatorios, máx. 100', () => {
    expect(issues({ ...valid, first_name: ' ' }).first_name).toBeTruthy()
    expect(issues({ ...valid, last_name: 'x'.repeat(101) }).last_name).toBeTruthy()
  })

  it('contraseña: aplica la política y reporta una razón legible', () => {
    expect(issues({ ...valid, password: 'corta' }).password).toMatch(/requisitos/)
    expect(issues({ ...valid, password: 'sinmayuscula-2026!' }).password).toMatch(/requisitos/)
    expect(issues({ ...valid, password: 'Contiene-ana.perez-1' }).password).toBeUndefined() // el usuario ya no está prohibido
    expect(issues({ ...valid, username: 'otro.u', password: 'Contiene-ANA-1234' }).password).toBeUndefined() // ni la parte local del correo
    expect(issues({ ...valid, password: '' }).password).toBeTruthy()
  })

  it('contraseña: usa la política vigente del servidor al validar', () => {
    policy = { ...STRICT, min_length: 4, require_uppercase: false, require_digit: false, require_symbol: false }
    expect(issues({ ...valid, password: 'corta' }).password).toBeUndefined()
    policy = STRICT
    expect(issues({ ...valid, password: 'corta' }).password).toBeTruthy()
  })
})

describe('userEditSchema', () => {
  it('no incluye usuario (inmutable) ni contraseña', () => {
    const { username: _u, password: _p, ...rest } = valid
    expect(userEditSchema.parse(rest)).toEqual(rest)
    expect(Object.keys(userEditSchema.shape)).not.toContain('username')
    expect(Object.keys(userEditSchema.shape)).not.toContain('password')
  })
})

describe('passwordResetSchema', () => {
  it('valida con la política del servidor', () => {
    const schema = passwordResetSchema(() => STRICT)
    expect(schema.safeParse({ password: 'Segura-Clave-2026' }).success).toBe(true)
    expect(schema.safeParse({ password: 'Segura-ana-2026' }).success).toBe(true) // contener el usuario ya no se rechaza
    expect(schema.safeParse({ password: 'corta' }).success).toBe(false)
  })
})
