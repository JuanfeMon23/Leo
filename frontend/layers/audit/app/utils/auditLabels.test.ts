import { describe, expect, it } from 'vitest'
import type { AuditApplicationDetail, AuditCatalog, AuditEventRead } from '../types/audit'
import {
  auditActionName, auditActorLabel, auditApplicationName, auditCatalogFrom, auditEntityLabel, auditModuleName, auditResultLabel, auditResultVariant
} from './auditLabels'

const detail = (over: Partial<AuditApplicationDetail> = {}): AuditApplicationDetail => ({
  id: 'a1', slug: 'leo', name: 'Leo',
  modules: [{ slug: 'users', name: 'Usuarios', actions: [{ tag: 'leo.users.edit', name: 'Editar usuario' }] }],
  ...over
})
const catalog = (): AuditCatalog => auditCatalogFrom([detail()])
const event = (over: Partial<AuditEventRead> = {}): AuditEventRead => ({
  id: 'e1', occurred_at: '', actor_user_id: null, actor_username: null, application_id: 'a1', module: 'users', action_tag: 'leo.users.edit',
  entity_type: 'user', entity_id: '42', changes: null, result: 'ok', reason: null, ip: null, user_agent: null, session_id: null, request_id: null, ...over
})

describe('resultado', () => {
  it('etiquetas legibles', () => {
    expect(auditResultLabel('ok')).toBe('Permitido')
    expect(auditResultLabel('denied')).toBe('Denegado')
    expect(auditResultLabel('error')).toBe('Error')
  })

  it('colores: verde, ámbar y rojo', () => {
    expect(auditResultVariant('ok')).toBe('success')
    expect(auditResultVariant('denied')).toBe('warning')
    expect(auditResultVariant('error')).toBe('danger')
  })
})

describe('nombres desde el catálogo', () => {
  it('aplicación, módulo y acción por su nombre', () => {
    const c = catalog()
    expect(auditApplicationName(c, 'a1')).toBe('Leo')
    expect(auditModuleName(c, 'a1', 'users')).toBe('Usuarios')
    expect(auditActionName(c, 'a1', 'leo.users.edit')).toBe('Editar usuario')
  })

  it('sin catálogo cae en el identificador técnico', () => {
    expect(auditApplicationName({}, 'a1')).toBe('Aplicación desconocida')
    expect(auditModuleName({}, 'a1', 'users')).toBe('users')
    expect(auditActionName({}, 'a1', 'leo.users.edit')).toBe('leo.users.edit')
  })

  it('un evento sin módulo muestra «—»', () => {
    expect(auditModuleName(catalog(), 'a1', null)).toBe('—')
  })

  it('el catálogo se indexa por id de aplicación', () => {
    expect(Object.keys(catalog())).toEqual(['a1'])
  })
})

describe('actor y entidad', () => {
  it('sin usuario el actor es el sistema', () => {
    expect(auditActorLabel(event())).toBe('Sistema')
    expect(auditActorLabel(event({ actor_username: 'ana' }))).toBe('ana')
  })

  it('entidad: tipo legible + identificador', () => {
    expect(auditEntityLabel(event())).toEqual({ type: 'Usuario', id: '42' })
    expect(auditEntityLabel(event({ entity_type: 'session', entity_id: null }))).toEqual({ type: 'Sesión', id: null })
    expect(auditEntityLabel(event({ entity_type: 'widget' }))).toEqual({ type: 'widget', id: '42' })
  })

  it('sin entidad devuelve null', () => {
    expect(auditEntityLabel(event({ entity_type: null, entity_id: null }))).toBeNull()
  })
})
