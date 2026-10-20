import { describe, expect, it } from 'vitest'
import { SLUG_MESSAGE, SLUG_REGEX, zSlug } from './slug'

describe('zSlug', () => {
  it('acepta kebab-case y recorta', () => {
    expect(zSlug('obligatorio').parse(' mi-app ')).toBe('mi-app')
  })

  it.each(['Mi', 'a b', 'a--b', '-a', 'a-', 'a_b'])('rechaza %s', (v) => {
    const r = zSlug('obligatorio').safeParse(v)
    expect(r.success).toBe(false)
    expect(r.error!.issues.map(i => i.message)).toContain(SLUG_MESSAGE)
    expect(SLUG_REGEX.test(v)).toBe(false)
  })

  it('obligatorio y máximo 64', () => {
    expect(zSlug('Falta.').safeParse('').error!.issues[0]!.message).toBe('Falta.')
    expect(zSlug('x').safeParse('a'.repeat(65)).success).toBe(false)
    expect(zSlug('x').safeParse('a'.repeat(64)).success).toBe(true)
  })
})
