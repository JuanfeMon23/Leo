import { describe, expect, it } from 'vitest'
import {
  actionCreateSchema,
  actionEditSchema,
  applicationCreateSchema,
  applicationEditSchema,
  moduleCreateSchema,
  moduleEditSchema,
  redirectUrisToText
} from './applicationSchemas'

const valid = { slug: 'vladimir', name: ' Vladimir ', description: '', base_url: 'https://vladimir.test', redirect_uris: '' }

function messages(result: { success: boolean, error?: { issues: { message: string }[] } }) {
  return result.success ? [] : result.error!.issues.map(i => i.message)
}

describe('applicationCreateSchema', () => {
  it('valida y entrega el payload del backend (recortado, null, lista sin repetidos)', () => {
    const r = applicationCreateSchema.parse({ ...valid, redirect_uris: 'https://a.test/cb\n\n  https://b.test/cb  \nhttps://a.test/cb' })
    expect(r).toEqual({
      slug: 'vladimir',
      name: 'Vladimir',
      description: null,
      base_url: 'https://vladimir.test',
      redirect_uris: ['https://a.test/cb', 'https://b.test/cb']
    })
  })

  it('redirect_uris vacío es lista vacía', () => {
    expect(applicationCreateSchema.parse(valid).redirect_uris).toEqual([])
  })

  it.each(['Vladimir', 'a b', 'a--b', '-a', 'a-', 'a_b', 'á'])('slug inválido %s', (slug) => {
    expect(messages(applicationCreateSchema.safeParse({ ...valid, slug }))).toContain(
      'Usa minúsculas, números y guiones (kebab-case), por ejemplo «mi-app».'
    )
  })

  it('slug obligatorio y máximo 64', () => {
    expect(messages(applicationCreateSchema.safeParse({ ...valid, slug: '' }))).toContain('El identificador es obligatorio.')
    expect(messages(applicationCreateSchema.safeParse({ ...valid, slug: 'a'.repeat(65) }))).toContain('Máximo 64 caracteres.')
    expect(applicationCreateSchema.safeParse({ ...valid, slug: 'a'.repeat(64) }).success).toBe(true)
  })

  it('nombre obligatorio y máximo 128', () => {
    expect(messages(applicationCreateSchema.safeParse({ ...valid, name: '  ' }))).toContain('El nombre es obligatorio.')
    expect(messages(applicationCreateSchema.safeParse({ ...valid, name: 'a'.repeat(129) }))).toContain('Máximo 128 caracteres.')
  })

  it('descripción máximo 2000', () => {
    expect(applicationCreateSchema.safeParse({ ...valid, description: 'a'.repeat(2001) }).success).toBe(false)
  })

  it.each(['', 'vladimir.test', 'ftp://x.test', 'https://x.test/#a', 'https://', 'javascript:alert(1)'])('base_url inválida «%s»', (base_url) => {
    expect(applicationCreateSchema.safeParse({ ...valid, base_url }).success).toBe(false)
  })

  it('base_url http(s) válida (también con puerto)', () => {
    expect(applicationCreateSchema.safeParse({ ...valid, base_url: 'http://localhost:3000' }).success).toBe(true)
  })

  it('una redirect_uri inválida dice cuál línea', () => {
    const r = applicationCreateSchema.safeParse({ ...valid, redirect_uris: 'https://a.test/cb\nnope' })
    expect(messages(r)).toEqual(['Línea 2: debe ser una URL absoluta http o https.'])
  })

  it('redirect_uri con fragmento es inválida', () => {
    expect(messages(applicationCreateSchema.safeParse({ ...valid, redirect_uris: 'https://a.test/cb#x' }))).toEqual([
      'Línea 1: no puede tener fragmento (#).'
    ])
  })

  it('máximo 20 redirect_uris', () => {
    const many = (n: number) => Array.from({ length: n }, (_, i) => `https://a.test/${i}`).join('\n')
    expect(applicationCreateSchema.safeParse({ ...valid, redirect_uris: many(20) }).success).toBe(true)
    expect(messages(applicationCreateSchema.safeParse({ ...valid, redirect_uris: many(21) }))).toContain('Máximo 20 redirect URIs.')
  })
})

describe('applicationEditSchema', () => {
  it('no incluye el slug (inmutable)', () => {
    const r = applicationEditSchema.parse({ name: 'N', description: 'd', base_url: 'https://x.test', redirect_uris: '', slug: 'otro' })
    expect(r).not.toHaveProperty('slug')
  })
})

describe('redirectUrisToText', () => {
  it('une con saltos de línea', () => {
    expect(redirectUrisToText(['https://a.test/1', 'https://b.test/2'])).toBe('https://a.test/1\nhttps://b.test/2')
    expect(redirectUrisToText([])).toBe('')
  })
})

describe('moduleCreateSchema / moduleEditSchema', () => {
  it('crea con slug kebab-case', () => {
    expect(moduleCreateSchema.parse({ slug: 'samples', name: 'Muestras', description: ' ' })).toEqual({
      slug: 'samples', name: 'Muestras', description: null
    })
    expect(moduleCreateSchema.safeParse({ slug: 'Muestras', name: 'x', description: '' }).success).toBe(false)
  })

  it('editar no acepta cambiar el slug', () => {
    expect(moduleEditSchema.parse({ name: 'N', description: '', slug: 'x' })).toEqual({ name: 'N', description: null })
  })
})

describe('actionCreateSchema', () => {
  it('verbo kebab-case, nombre legible y descripción opcional', () => {
    expect(actionCreateSchema.parse({ verb: 'rotate-secret', name: ' Rotar secreto ', description: '' })).toEqual({
      verb: 'rotate-secret', name: 'Rotar secreto', description: null
    })
  })

  it('verbo obligatorio e inválido', () => {
    expect(messages(actionCreateSchema.safeParse({ verb: '', name: 'N', description: '' }))).toContain('El verbo es obligatorio.')
    expect(actionCreateSchema.safeParse({ verb: 'Edit', name: 'N', description: '' }).success).toBe(false)
  })

  it('nombre obligatorio (también solo espacios) y máximo 120', () => {
    expect(messages(actionCreateSchema.safeParse({ verb: 'view', name: '', description: '' }))).toContain('El nombre del permiso es obligatorio.')
    expect(messages(actionCreateSchema.safeParse({ verb: 'view', name: '   ', description: '' }))).toContain('El nombre del permiso es obligatorio.')
    expect(actionCreateSchema.safeParse({ verb: 'view', name: 'a'.repeat(120), description: '' }).success).toBe(true)
    expect(messages(actionCreateSchema.safeParse({ verb: 'view', name: 'a'.repeat(121), description: '' }))).toContain('Máximo 120 caracteres.')
  })
})

describe('actionEditSchema', () => {
  it('permite cambiar nombre y descripción; el verbo (inmutable) no forma parte', () => {
    expect(actionEditSchema.parse({ name: 'Consultar', description: 'x', verb: 'otro' })).toEqual({ name: 'Consultar', description: 'x' })
    expect(actionEditSchema.safeParse({ name: '', description: '' }).success).toBe(false)
  })
})
