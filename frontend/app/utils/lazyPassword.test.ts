import { describe, expect, it } from 'vitest'
import type { PasswordPolicy } from '#andromeda/utils/passwordPolicy'
import { zLazyPassword } from './lazyPassword'

const STRICT: PasswordPolicy = {
  min_length: 12, max_length: 128, require_lowercase: true, require_uppercase: true, require_digit: true, require_symbol: true
}

describe('zLazyPassword', () => {
  it('valida con la política vigente en cada validación', () => {
    let policy = STRICT
    const field = zLazyPassword(() => policy)
    expect(field.safeParse('corta').success).toBe(false)
    expect(field.safeParse('Segura-Clave-2026').success).toBe(true)
    policy = { ...STRICT, min_length: 4, require_uppercase: false, require_digit: false, require_symbol: false }
    expect(field.safeParse('corta').success).toBe(true)
  })

  it('vacía: mensaje de obligatoria; sin cumplir: mensaje de requisitos pendientes', () => {
    const field = zLazyPassword(() => STRICT)
    expect(field.safeParse('').error?.issues[0]?.message).toBe('Escribe una contraseña.')
    expect(field.safeParse('abc').error?.issues[0]?.message).toMatch(/requisitos/)
  })
})
