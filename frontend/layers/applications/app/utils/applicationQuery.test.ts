import { describe, expect, it } from 'vitest'
import { buildApplicationsQuery, APPLICATIONS_PAGE_SIZE } from './applicationQuery'

describe('buildApplicationsQuery', () => {
  it('sin filtros: solo paginación', () => {
    expect(buildApplicationsQuery({ search: '', page: 1, active: undefined })).toEqual({ page: 1, page_size: APPLICATIONS_PAGE_SIZE })
  })

  it('con búsqueda normalizada y filtro de estado', () => {
    expect(buildApplicationsQuery({ search: '  mi   app ', page: 3, active: false })).toEqual({
      page: 3, page_size: APPLICATIONS_PAGE_SIZE, q: 'mi app', active: false
    })
    expect(buildApplicationsQuery({ search: '', page: 1, active: true }).active).toBe(true)
  })
})
