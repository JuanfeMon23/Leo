import { describe, expect, it } from 'vitest'
import { EVENT_PREFIX, isEventAction } from './actionEvents'

describe('isEventAction', () => {
  it('descripción que empieza por "Evento:"', () => {
    expect(isEventAction('Evento: inicio de sesion')).toBe(true)
    expect(isEventAction('  Evento: x')).toBe(true)
    expect(EVENT_PREFIX).toBe('Evento:')
  })

  it('otras descripciones o vacías no son evento', () => {
    expect(isEventAction('Ver usuarios')).toBe(false)
    expect(isEventAction('El Evento: no al inicio')).toBe(false)
    expect(isEventAction(null)).toBe(false)
    expect(isEventAction(undefined)).toBe(false)
  })
})
