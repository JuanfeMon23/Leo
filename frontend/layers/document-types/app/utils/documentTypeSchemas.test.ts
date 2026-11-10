import { describe, expect, it } from 'vitest'
import { documentTypeCreateSchema } from './documentTypeSchemas'

const issues = (input: unknown) => {
  const result = documentTypeCreateSchema.safeParse(input)
  return result.success ? {} : Object.fromEntries(result.error.issues.map(issue => [issue.path.join('.'), issue.message])) as Record<string, string>
}

describe('documentTypeCreateSchema', () => {
  it('normaliza el código a mayúsculas y el orden a número', () => {
    expect(documentTypeCreateSchema.parse({ code: ' cc ', name: ' Cédula ', sort_order: '10' })).toEqual({ code: 'CC', name: 'Cédula', sort_order: 10 })
  })

  it('código y nombre obligatorios', () => {
    expect(issues({ code: '', name: 'x', sort_order: 1 }).code).toBeTruthy()
    expect(issues({ code: 'CC', name: '  ', sort_order: 1 }).name).toBeTruthy()
  })

  it('orden: obligatorio, entero y no negativo', () => {
    expect(issues({ code: 'CC', name: 'x', sort_order: '' }).sort_order).toMatch(/obligatorio/)
    expect(issues({ code: 'CC', name: 'x', sort_order: '1.5' }).sort_order).toMatch(/entero/)
    expect(issues({ code: 'CC', name: 'x', sort_order: 'abc' }).sort_order).toBeTruthy()
    expect(issues({ code: 'CC', name: 'x', sort_order: '-1' }).sort_order).toMatch(/negativo/)
    expect(issues({ code: 'CC', name: 'x', sort_order: '0' }).sort_order).toBeUndefined()
  })
})
