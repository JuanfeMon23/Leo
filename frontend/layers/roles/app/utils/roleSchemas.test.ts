import { describe, expect, it } from 'vitest'
import { roleCreateSchema, roleEditSchema } from './roleSchemas'

const valid = { application_id: 'app-1', slug: 'lab-admin', name: ' Administrador ', description: '' }
const messages = (r: { success: boolean, error?: { issues: { message: string }[] } }) => (r.success ? [] : r.error!.issues.map(i => i.message))

describe('roleCreateSchema', () => {
  it('entrega el payload del backend (recortado, descripción null)', () => {
    expect(roleCreateSchema.parse(valid)).toEqual({ application_id: 'app-1', slug: 'lab-admin', name: 'Administrador', description: null })
  })

  it('aplicación obligatoria', () => {
    expect(messages(roleCreateSchema.safeParse({ ...valid, application_id: '' }))).toContain('Elige la aplicación del rol.')
  })

  it.each(['Lab', 'a b', 'a--b', '-a', 'a_b'])('slug inválido %s', (slug) => {
    expect(roleCreateSchema.safeParse({ ...valid, slug }).success).toBe(false)
  })

  it('slug obligatorio, máx. 64', () => {
    expect(messages(roleCreateSchema.safeParse({ ...valid, slug: '' }))).toContain('El identificador es obligatorio.')
    expect(roleCreateSchema.safeParse({ ...valid, slug: 'a'.repeat(65) }).success).toBe(false)
  })

  it('nombre obligatorio y máx. 128; descripción máx. 2000', () => {
    expect(messages(roleCreateSchema.safeParse({ ...valid, name: '  ' }))).toContain('El nombre es obligatorio.')
    expect(roleCreateSchema.safeParse({ ...valid, name: 'a'.repeat(129) }).success).toBe(false)
    expect(roleCreateSchema.safeParse({ ...valid, description: 'a'.repeat(2001) }).success).toBe(false)
  })
})

describe('roleEditSchema', () => {
  it('no incluye slug ni aplicación (inmutables)', () => {
    expect(roleEditSchema.parse({ ...valid, name: 'Nuevo' })).toEqual({ name: 'Nuevo', description: null })
  })
})
