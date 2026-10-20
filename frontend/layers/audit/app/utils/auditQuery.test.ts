import { describe, expect, it } from 'vitest'
import type { AuditFiltersState } from '../types/audit'
import {
  AUDIT_PAGE_SIZE, auditActiveFilterCount, buildAuditFilterParams, buildAuditQuery, dayEndExclusiveIso, dayStartIso, emptyAuditFilters
} from './auditQuery'

const filters = (over: Partial<AuditFiltersState> = {}): AuditFiltersState => ({ ...emptyAuditFilters(), ...over })

describe('dayStartIso / dayEndExclusiveIso', () => {
  it('el día local empieza a las 00:00 y termina (excluido) a las 00:00 del siguiente', () => {
    expect(dayStartIso('2026-10-01')).toBe(new Date(2026, 9, 1).toISOString())
    expect(dayEndExclusiveIso('2026-10-01')).toBe(new Date(2026, 9, 2).toISOString())
  })

  it('el fin de mes salta al mes siguiente', () => {
    expect(dayEndExclusiveIso('2026-10-31')).toBe(new Date(2026, 10, 1).toISOString())
  })

  it('una fecha vacía o mal formada no produce valor', () => {
    expect(dayStartIso('')).toBeUndefined()
    expect(dayEndExclusiveIso('31/10/2026')).toBeUndefined()
  })
})

describe('buildAuditFilterParams', () => {
  it('sin filtros no envía nada', () => {
    expect(buildAuditFilterParams(filters())).toEqual({})
  })

  it('traduce cada filtro a su parámetro del backend', () => {
    expect(buildAuditFilterParams(filters({
      actorUserId: 'u1', applicationId: 'a1', module: 'users', actionTag: 'leo.users.edit',
      entityType: 'user', entityId: '42', result: 'denied', dateFrom: '2026-10-01', dateTo: '2026-10-19'
    }))).toEqual({
      actor_user_id: 'u1', application_id: 'a1', module: 'users', action_tag: 'leo.users.edit',
      entity_type: 'user', entity_id: '42', result: 'denied',
      date_from: new Date(2026, 9, 1).toISOString(), date_to: new Date(2026, 9, 20).toISOString()
    })
  })

  it('recorta los textos y omite los vacíos', () => {
    expect(buildAuditFilterParams(filters({ actorUsername: '  ana ', entityId: '   ' }))).toEqual({ actor_username: 'ana' })
  })
})

describe('buildAuditQuery', () => {
  it('añade página y tamaño a los filtros', () => {
    expect(buildAuditQuery(filters({ result: 'ok' }), 3)).toEqual({ page: 3, page_size: AUDIT_PAGE_SIZE, result: 'ok' })
  })
})

describe('auditActiveFilterCount', () => {
  it('cuenta los filtros con valor', () => {
    expect(auditActiveFilterCount(filters())).toBe(0)
    expect(auditActiveFilterCount(filters({ result: 'ok', dateFrom: '2026-10-01', entityId: ' ' }))).toBe(2)
  })
})
