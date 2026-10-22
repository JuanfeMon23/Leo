import { describe, expect, it } from 'vitest'
import { zEmail } from './email'

describe('zEmail', () => {
  it('recorta espacios y acepta la forma a@b', () => {
    expect(zEmail.parse('  ana@x.co ')).toBe('ana@x.co')
  })

  it.each(['', '   ', 'sin-arroba', 'a b@x.co', 'a@b c'])('rechaza «%s»', (v) => {
    expect(zEmail.safeParse(v).success).toBe(false)
  })

  it('máximo 254 caracteres', () => {
    expect(zEmail.safeParse(`${'a'.repeat(250)}@x.co`).success).toBe(false)
    expect(zEmail.safeParse(`${'a'.repeat(246)}@x.co`).success).toBe(true)
  })
})
