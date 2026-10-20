import { describe, expect, it } from 'vitest'
import type { UserRead } from '../types/users'
import { usersDocument, usersFormatDateTime, usersFullName, usersStatus } from './userDisplay'

const user = (over: Partial<UserRead> = {}): UserRead => ({
  id: 'u1', username: 'ana', email: 'a@x.co', document_type: 'CC', document_number: '123',
  first_name: 'Ana María', last_name: 'Pérez', is_active: true, last_login_at: null,
  failed_login_attempts: 0, locked_until: null, created_at: '', updated_at: '', ...over
})
const NOW = new Date(2026, 9, 19, 10, 0, 0)

describe('usersFullName / usersDocument', () => {
  it('nombres y apellidos', () => {
    expect(usersFullName(user())).toBe('Ana María Pérez')
  })
  it('tipo + número', () => {
    expect(usersDocument(user())).toBe('CC 123')
  })
})

describe('usersStatus', () => {
  it('activo e inactivo', () => {
    expect(usersStatus(user(), NOW)).toEqual({ kind: 'active', label: 'Activo' })
    expect(usersStatus(user({ is_active: false }), NOW)).toEqual({ kind: 'inactive', label: 'Inactivo' })
  })

  it('bloqueado hasta HH:MM (hora local) si el bloqueo sigue vigente', () => {
    const until = new Date(2026, 9, 19, 10, 15, 0).toISOString()
    expect(usersStatus(user({ locked_until: until }), NOW)).toEqual({ kind: 'locked', label: 'Bloqueado hasta 10:15' })
  })

  it('un bloqueo vencido no cuenta', () => {
    const past = new Date(2026, 9, 19, 9, 0, 0).toISOString()
    expect(usersStatus(user({ locked_until: past }), NOW).kind).toBe('active')
  })

  it('inactivo manda sobre bloqueado', () => {
    const until = new Date(2026, 9, 19, 10, 15, 0).toISOString()
    expect(usersStatus(user({ is_active: false, locked_until: until }), NOW).kind).toBe('inactive')
  })

  it('si el bloqueo es de otro día se indica la fecha', () => {
    const until = new Date(2026, 9, 20, 8, 5, 0).toISOString()
    expect(usersStatus(user({ locked_until: until }), NOW).label).toBe('Bloqueado hasta 20/10/2026 08:05')
  })
})

describe('usersFormatDateTime', () => {
  it('formatea en hora local', () => {
    expect(usersFormatDateTime(new Date(2026, 0, 5, 7, 9).toISOString())).toBe('05/01/2026 07:09')
  })
  it('nulo o inválido → «Nunca»', () => {
    expect(usersFormatDateTime(null)).toBe('Nunca')
    expect(usersFormatDateTime('no-fecha')).toBe('Nunca')
  })
})
