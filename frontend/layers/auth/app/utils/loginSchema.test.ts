import { describe, expect, it } from 'vitest'
import { loginSchema } from './loginSchema'

describe('loginSchema', () => {
  it('acepta usuario o email y contraseña, recortando el usuario', () => {
    expect(loginSchema.parse({ login: '  ana@x.co ', password: 'secreto' })).toEqual({ login: 'ana@x.co', password: 'secreto' })
  })

  it('no recorta la contraseña', () => {
    expect(loginSchema.parse({ login: 'ana', password: ' a b ' }).password).toBe(' a b ')
  })

  it('exige usuario y contraseña con mensajes en español', () => {
    const result = loginSchema.safeParse({ login: '   ', password: '' })
    expect(result.success).toBe(false)
    const messages = result.error!.issues.map(i => i.message)
    expect(messages).toContain('Ingresa tu usuario o correo electrónico.')
    expect(messages).toContain('Ingresa tu contraseña.')
  })

  it('respeta los máximos del backend (254 y 1024)', () => {
    expect(loginSchema.safeParse({ login: 'a'.repeat(255), password: 'x' }).success).toBe(false)
    expect(loginSchema.safeParse({ login: 'a'.repeat(254), password: 'x'.repeat(1025) }).success).toBe(false)
    expect(loginSchema.safeParse({ login: 'a'.repeat(254), password: 'x'.repeat(1024) }).success).toBe(true)
  })
})
