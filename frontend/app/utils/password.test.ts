import { describe, expect, it } from 'vitest'
import { passwordProblems, passwordRequirements } from './password'

const met = (password: string, ctx = {}) =>
  Object.fromEntries(passwordRequirements(password, ctx).map(r => [r.id, r.met]))

describe('passwordRequirements', () => {
  it('lista los 6 requisitos del backend, con texto legible', () => {
    const reqs = passwordRequirements('')
    expect(reqs.map(r => r.id)).toEqual(['length', 'lower', 'upper', 'digit', 'symbol', 'personal'])
    expect(reqs.every(r => r.label.length > 5)).toBe(true)
  })

  it('largo: 12 a 128 caracteres', () => {
    expect(met('a'.repeat(11)).length).toBe(false)
    expect(met('a'.repeat(12)).length).toBe(true)
    expect(met('a'.repeat(128)).length).toBe(true)
    expect(met('a'.repeat(129)).length).toBe(false)
  })

  it('minúscula, mayúscula, dígito y símbolo', () => {
    expect(met('ABC')).toMatchObject({ lower: false, upper: true, digit: false, symbol: false })
    expect(met('abc1!')).toMatchObject({ lower: true, upper: false, digit: true, symbol: true })
    expect(met('ñÑ')).toMatchObject({ lower: true, upper: true })
  })

  it('no contiene el usuario ni la parte local del correo (≥3 letras, sin distinguir mayúsculas)', () => {
    expect(met('xxAnaLopezxx', { username: 'analopez' }).personal).toBe(false)
    expect(met('xxANALOPEZxx', { username: 'analopez' }).personal).toBe(false)
    expect(met('xxjuanxx', { email: 'juan@x.co' }).personal).toBe(false)
    expect(met('xxdominioxx', { email: 'juan@dominio.co' }).personal).toBe(true) // solo la parte local
    expect(met('zzabzz', { username: 'ab' }).personal).toBe(true) // <3: no cuenta
    expect(met('anything', {}).personal).toBe(true)
  })
})

describe('passwordProblems', () => {
  it('vacío para una contraseña fuerte', () => {
    expect(passwordProblems('Segura-Clave-2026', { username: 'ana', email: 'a@x.co' })).toEqual([])
  })

  it('devuelve las etiquetas de lo que falta', () => {
    expect(passwordProblems('corta').length).toBe(4) // largo, mayúscula, dígito, símbolo
  })
})
