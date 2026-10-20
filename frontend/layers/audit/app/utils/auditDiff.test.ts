import { describe, expect, it } from 'vitest'
import { MASKED_VALUE, auditDiffRows, auditFieldLabel, auditFormatValue } from './auditDiff'

describe('auditFormatValue', () => {
  it('textos tal cual; vacío y null como «(vacío)»', () => {
    expect(auditFormatValue('Ana')).toBe('Ana')
    expect(auditFormatValue(null)).toBe('(vacío)')
    expect(auditFormatValue(undefined)).toBe('(vacío)')
    expect(auditFormatValue('')).toBe('(vacío)')
  })

  it('booleanos como Sí / No y números tal cual', () => {
    expect(auditFormatValue(true)).toBe('Sí')
    expect(auditFormatValue(false)).toBe('No')
    expect(auditFormatValue(0)).toBe('0')
  })

  it('listas y objetos en forma compacta legible', () => {
    expect(auditFormatValue(['a', 'b'])).toBe('a, b')
    expect(auditFormatValue([])).toBe('(vacío)')
    expect(auditFormatValue({ x: 1 })).toBe('{"x":1}')
  })
})

describe('auditFieldLabel', () => {
  it('traduce los campos conocidos y deja el resto como viene', () => {
    expect(auditFieldLabel('is_active')).toBe('Activo')
    expect(auditFieldLabel('revoked_reason')).toBe('Motivo de revocación')
    expect(auditFieldLabel('campo_raro')).toBe('campo_raro')
  })
})

describe('auditDiffRows', () => {
  it('sin cambios devuelve lista vacía', () => {
    expect(auditDiffRows(null)).toEqual([])
    expect(auditDiffRows({})).toEqual([])
  })

  it('marca lo cambiado, lo agregado y lo quitado, ordenado por campo', () => {
    const rows = auditDiffRows({
      name: { before: 'A', after: 'B' },
      description: { before: null, after: 'nueva' },
      email: { before: 'x@y.co', after: null },
      same: { before: 1, after: 1 }
    })
    expect(rows.map(r => [r.field, r.kind, r.before, r.after])).toEqual([
      ['description', 'added', '(vacío)', 'nueva'],
      ['email', 'removed', 'x@y.co', '(vacío)'],
      ['name', 'changed', 'A', 'B'],
      ['same', 'unchanged', '1', '1']
    ])
  })

  it('compara por valor (listas y objetos)', () => {
    const [row] = auditDiffRows({ redirect_uris: { before: ['a'], after: ['a'] } })
    expect(row?.kind).toBe('unchanged')
  })

  it('nunca muestra valores de campos sensibles', () => {
    const rows = auditDiffRows({
      password_hash: { before: 'abc', after: 'def' },
      client_secret: { before: 'x', after: 'y' }
    })
    expect(rows).toHaveLength(2)
    for (const row of rows) {
      expect(row.sensitive).toBe(true)
      expect(row.before).toBe(MASKED_VALUE)
      expect(row.after).toBe(MASKED_VALUE)
      expect(row.kind).toBe('changed')
    }
  })

  it('un valor que no es {before, after} se muestra como «después»', () => {
    const [row] = auditDiffRows({ nota: 'hola' })
    expect(row).toMatchObject({ field: 'nota', kind: 'added', before: '(vacío)', after: 'hola' })
  })
})
