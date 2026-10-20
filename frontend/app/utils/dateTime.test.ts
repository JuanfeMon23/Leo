import { describe, expect, it } from 'vitest'
import { formatLocalDateTime } from './dateTime'

describe('formatLocalDateTime', () => {
  it('DD/MM/AAAA HH:MM en hora local', () => {
    expect(formatLocalDateTime(new Date(2026, 0, 5, 7, 9, 3).toISOString())).toBe('05/01/2026 07:09')
  })

  it('con segundos cuando se pide', () => {
    expect(formatLocalDateTime(new Date(2026, 0, 5, 7, 9, 3).toISOString(), { seconds: true })).toBe('05/01/2026 07:09:03')
  })

  it('sin fecha o inválida devuelve el texto de respaldo', () => {
    expect(formatLocalDateTime(null)).toBe('—')
    expect(formatLocalDateTime('basura')).toBe('—')
    expect(formatLocalDateTime(undefined, { fallback: 'Nunca' })).toBe('Nunca')
  })
})
