import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { clearDocumentTypesCache, useDocumentTypes } from './useDocumentTypes'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const TYPES = [
  { code: 'CC', name: 'Cédula de ciudadanía', sort_order: 10, is_active: true },
  { code: 'OLD', name: 'Tipo antiguo', sort_order: 99, is_active: false }
]

beforeEach(() => {
  api.mockReset()
  clearDocumentTypesCache()
  api.mockImplementation(async (_url: string, options: { query: { active: boolean } }) =>
    TYPES.filter(type => type.is_active === options.query.active))
})

describe('useDocumentTypes', () => {
  it('carga el catálogo y nombra cada código; uno desconocido se muestra como su código', async () => {
    const catalog = useDocumentTypes()
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/document-types', { query: { active: true } })
    expect(api).toHaveBeenCalledWith('/document-types', { query: { active: false } })
    expect(catalog.nameOf('CC')).toBe('Cédula de ciudadanía')
    expect(catalog.nameOf('ZZ')).toBe('ZZ')
  })

  it('las opciones del selector son los activos, más el código actual aunque esté inactivo', async () => {
    const catalog = useDocumentTypes()
    await flushPromises()
    expect(catalog.selectOptions()).toEqual([{ value: 'CC', label: 'CC · Cédula de ciudadanía' }])
    expect(catalog.selectOptions('OLD')).toEqual([
      { value: 'CC', label: 'CC · Cédula de ciudadanía' },
      { value: 'OLD', label: 'OLD · Tipo antiguo (inactivo)' }
    ])
  })

  it('reutiliza la caché entre usos y vuelve a pedir tras limpiarla', async () => {
    useDocumentTypes()
    await flushPromises()
    const second = useDocumentTypes()
    await flushPromises()
    expect(api).toHaveBeenCalledTimes(2)
    expect(second.types.value).toHaveLength(2)
    clearDocumentTypesCache()
    useDocumentTypes()
    await flushPromises()
    expect(api).toHaveBeenCalledTimes(4)
  })

  it('usos simultáneos comparten una sola petición', async () => {
    useDocumentTypes()
    useDocumentTypes()
    await flushPromises()
    expect(api).toHaveBeenCalledTimes(2)
  })

  it('une activos e inactivos ordenados por orden y código', async () => {
    api.mockImplementation(async (_url: string, options: { query: { active: boolean } }) => options.query.active
      ? [{ code: 'B', name: 'b', sort_order: 1, is_active: true }, { code: 'C', name: 'c', sort_order: 3, is_active: true }]
      : [{ code: 'A', name: 'a', sort_order: 1, is_active: false }, { code: 'Z', name: 'z', sort_order: 2, is_active: false }])
    const catalog = useDocumentTypes()
    await flushPromises()
    expect(catalog.types.value.map(type => type.code)).toEqual(['A', 'B', 'Z', 'C'])
  })

  it('si falla, deja un mensaje legible y la lista vacía', async () => {
    api.mockRejectedValue(new LeoApiError(500, 'internal_error', 'boom'))
    const catalog = useDocumentTypes()
    await flushPromises()
    expect(catalog.types.value).toEqual([])
    expect(catalog.error.value).toBeTruthy()
    expect(catalog.error.value).not.toMatch(/boom|internal_error/)
  })
})
