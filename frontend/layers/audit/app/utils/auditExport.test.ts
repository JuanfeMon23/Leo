import { describe, expect, it } from 'vitest'
import { emptyAuditFilters } from './auditQuery'
import { auditExportFilename } from './auditExport'

const NOW = new Date(2026, 9, 19, 10, 0, 0)

describe('auditExportFilename', () => {
  it('sin rango lleva la fecha de la exportación', () => {
    expect(auditExportFilename(emptyAuditFilters(), NOW)).toBe('auditoria-2026-10-19.csv')
  })

  it('con rango lo incluye', () => {
    expect(auditExportFilename({ ...emptyAuditFilters(), dateFrom: '2026-10-01', dateTo: '2026-10-15' }, NOW))
      .toBe('auditoria-2026-10-01_a_2026-10-15.csv')
  })

  it('con un solo extremo del rango', () => {
    expect(auditExportFilename({ ...emptyAuditFilters(), dateFrom: '2026-10-01' }, NOW)).toBe('auditoria-desde-2026-10-01.csv')
    expect(auditExportFilename({ ...emptyAuditFilters(), dateTo: '2026-10-15' }, NOW)).toBe('auditoria-hasta-2026-10-15.csv')
  })
})
