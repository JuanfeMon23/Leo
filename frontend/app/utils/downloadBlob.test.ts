import { describe, expect, it } from 'vitest'
import { safeDownloadName } from './downloadBlob'

describe('safeDownloadName', () => {
  it('conserva nombres normales', () => {
    expect(safeDownloadName('auditoria-2026-10-19.csv')).toBe('auditoria-2026-10-19.csv')
  })
  it('quita separadores de ruta y caracteres de control', () => {
    expect(safeDownloadName('../a\\b/c\u0000.csv')).toBe('a-b-c.csv')
  })
  it('nunca queda vacío', () => {
    expect(safeDownloadName('   ')).toBe('descarga')
  })
})

