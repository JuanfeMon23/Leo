import { describe, expect, it } from 'vitest'
import type { SessionRead } from '../types/sessions'
import { sessionCanRevoke, sessionOwnerLabel, sessionRevokedReasonLabel, sessionStatus, sessionStatusVariant } from './sessionStatus'

const NOW = new Date(2026, 9, 19, 10, 0, 0)
const session = (over: Partial<SessionRead> = {}): SessionRead => ({
  id: 's1', user_id: 'u1', ip: '10.0.0.1', user_agent: null,
  created_at: new Date(2026, 9, 19, 8, 0).toISOString(),
  last_activity_at: new Date(2026, 9, 19, 9, 50).toISOString(),
  expires_at: new Date(2026, 9, 19, 10, 20).toISOString(),
  revoked_at: null, revoked_reason: null, is_current: false, ...over
})

describe('sessionRevokedReasonLabel', () => {
  it('motivos conocidos en lenguaje de persona', () => {
    expect(sessionRevokedReasonLabel('logout')).toBe('Cierre de sesión')
    expect(sessionRevokedReasonLabel('admin')).toBe('Revocada por un administrador')
    expect(sessionRevokedReasonLabel('user-deactivated')).toBe('Usuario desactivado')
    expect(sessionRevokedReasonLabel('refresh-reuse')).toBe('Reúso de token (posible robo)')
    expect(sessionRevokedReasonLabel('idle-timeout')).toBe('Inactividad')
  })

  it('un motivo desconocido se muestra tal cual; vacío no inventa nada', () => {
    expect(sessionRevokedReasonLabel('otro')).toBe('otro')
    expect(sessionRevokedReasonLabel(null)).toBeNull()
  })
})

describe('sessionStatus', () => {
  it('activa: no revocada y sin vencer', () => {
    expect(sessionStatus(session(), NOW)).toEqual({ kind: 'active', label: 'Activa', reason: null })
  })

  it('inactiva por tiempo: venció sin revocarse', () => {
    const s = session({ expires_at: new Date(2026, 9, 19, 9, 59).toISOString() })
    expect(sessionStatus(s, NOW)).toEqual({ kind: 'idle', label: 'Inactiva por tiempo', reason: null })
  })

  it('revocada con su motivo legible (manda sobre el vencimiento)', () => {
    const s = session({ revoked_at: new Date(2026, 9, 19, 9, 0).toISOString(), revoked_reason: 'admin', expires_at: new Date(2026, 9, 19, 9, 30).toISOString() })
    expect(sessionStatus(s, NOW)).toEqual({ kind: 'revoked', label: 'Revocada', reason: 'Revocada por un administrador' })
  })
})

describe('sessionStatusVariant', () => {
  it('verde, gris y rojo', () => {
    expect(sessionStatusVariant('active')).toBe('success')
    expect(sessionStatusVariant('idle')).toBe('neutral')
    expect(sessionStatusVariant('revoked')).toBe('danger')
  })
})

describe('sessionCanRevoke', () => {
  it('solo se revoca una sesión activa', () => {
    expect(sessionCanRevoke(session(), NOW)).toBe(true)
    expect(sessionCanRevoke(session({ expires_at: new Date(2026, 9, 19, 9, 0).toISOString() }), NOW)).toBe(false)
    expect(sessionCanRevoke(session({ revoked_at: NOW.toISOString(), revoked_reason: 'logout' }), NOW)).toBe(false)
  })
})

describe('sessionOwnerLabel', () => {
  const users = [{ id: 'u1', username: 'ana', first_name: 'Ana', last_name: 'Pérez' }]
  it('nombre completo y usuario', () => {
    expect(sessionOwnerLabel('u1', users)).toEqual({ name: 'Ana Pérez', username: 'ana' })
  })
  it('usuario desconocido', () => {
    expect(sessionOwnerLabel('zzz', users)).toEqual({ name: 'Usuario desconocido', username: null })
  })
})
