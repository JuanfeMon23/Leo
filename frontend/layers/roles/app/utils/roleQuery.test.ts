import { describe, expect, it } from 'vitest'
import { ROLES_PAGE_SIZE, buildRolesQuery } from './roleQuery'

describe('buildRolesQuery', () => {
  it('solo página y tamaño cuando no hay filtros', () => {
    expect(buildRolesQuery({ search: '', page: 1, active: undefined, applicationId: '' })).toEqual({ page: 1, page_size: ROLES_PAGE_SIZE })
  })

  it('incluye búsqueda normalizada, estado (también false) y aplicación', () => {
    expect(buildRolesQuery({ search: '  admin  ', page: 2, active: false, applicationId: 'app-1' })).toEqual({
      page: 2, page_size: ROLES_PAGE_SIZE, q: 'admin', active: false, application_id: 'app-1'
    })
  })
})
