import { describe, expect, it } from 'vitest'
import { formatWait } from './formatWait'

describe('formatWait', () => {
  it.each([
    [1, '1 segundo'],
    [45, '45 segundos'],
    [60, '1 minuto'],
    [61, '2 minutos'],
    [299, '5 minutos'],
    [3600, '1 hora'],
    [5400, '2 horas']
  ])('%i s -> %s', (seconds, text) => {
    expect(formatWait(seconds)).toBe(text)
  })
})
