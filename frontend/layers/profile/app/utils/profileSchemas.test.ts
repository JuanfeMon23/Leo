import { describe, expect, it } from 'vitest'
import { passwordChangeSchema, profileSchema } from './profileSchemas'

type Parser = { safeParse: (v: unknown) => { success: boolean, error?: { issues: { path: (string | number)[], message: string }[] } } }

const issues = (schema: Parser, input: unknown) => {
  const r = schema.safeParse(input)
  return r.success ? {} : Object.fromEntries(r.error!.issues.map(i => [i.path.join('.'), i.message])) as Record<string, string>
}

describe('profileSchema', () => {
  const valid = { first_name: 'Ana', last_name: 'Pérez', email: 'ana@x.co' }

  it('recorta espacios', () => {
    expect(profileSchema.parse({ first_name: ' Ana ', last_name: ' Pérez ', email: ' ana@x.co ' })).toEqual(valid)
  })

  it('nombres y apellidos obligatorios, máximo 100', () => {
    expect(issues(profileSchema, { ...valid, first_name: '   ' }).first_name).toBeTruthy()
    expect(issues(profileSchema, { ...valid, last_name: '' }).last_name).toBeTruthy()
    expect(issues(profileSchema, { ...valid, first_name: 'a'.repeat(100) })).toEqual({})
    expect(issues(profileSchema, { ...valid, first_name: 'a'.repeat(101) }).first_name).toBeTruthy()
    expect(issues(profileSchema, { ...valid, last_name: 'a'.repeat(101) }).last_name).toBeTruthy()
  })

  it('correo válido y de máximo 254 caracteres', () => {
    expect(issues(profileSchema, { ...valid, email: 'sin-arroba' }).email).toBeTruthy()
    expect(issues(profileSchema, { ...valid, email: '' }).email).toBeTruthy()
    expect(issues(profileSchema, { ...valid, email: `${'a'.repeat(250)}@x.co` }).email).toMatch(/254/)
  })
})

describe('passwordChangeSchema', () => {
  const schema = passwordChangeSchema({ username: 'ana.perez', email: 'ana@x.co' })
  const valid = { current_password: 'Vieja-Clave-2025', new_password: 'Segura-Clave-2026', confirm_password: 'Segura-Clave-2026' }

  it('acepta una contraseña que cumple la política y coincide', () => {
    expect(issues(schema, valid)).toEqual({})
  })

  it('exige los tres campos', () => {
    const r = issues(schema, { current_password: '', new_password: '', confirm_password: '' })
    expect(r.current_password).toBeTruthy()
    expect(r.new_password).toBeTruthy()
    expect(r.confirm_password).toBeTruthy()
  })

  it('una contraseña débil dice qué falta', () => {
    expect(issues(schema, { ...valid, new_password: 'corta', confirm_password: 'corta' }).new_password).toMatch(/^Falta:/)
  })

  it('puede contener el usuario o la parte local del correo (ya no está prohibido)', () => {
    const r = issues(schema, { ...valid, new_password: 'Hola-ana.perez-2026', confirm_password: 'Hola-ana.perez-2026' })
    expect(r.new_password).toBeUndefined()
    const r2 = issues(schema, { ...valid, new_password: 'Hola-ANA-2026-x', confirm_password: 'Hola-ANA-2026-x' })
    expect(r2.new_password).toBeUndefined()
  })

  it('debe ser distinta de la actual', () => {
    expect(issues(schema, { ...valid, current_password: valid.new_password }).new_password).toMatch(/distinta de la actual/)
  })

  it('la confirmación debe coincidir', () => {
    expect(issues(schema, { ...valid, confirm_password: 'Otra-Clave-2026!' }).confirm_password).toMatch(/no coinciden/)
  })
})
