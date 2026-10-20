import { describe, expect, it } from 'vitest'
import { USERS_PAGE_SIZE, buildUsersQuery } from './userQuery'

describe('buildUsersQuery', () => {
  it('solo página y tamaño si no hay filtros', () => {
    expect(buildUsersQuery({ search: '', page: 1, active: undefined })).toEqual({ page: 1, page_size: USERS_PAGE_SIZE })
  })
  it('incluye q (normalizado) y active cuando tienen valor, también active=false', () => {
    expect(buildUsersQuery({ search: '  ana ', page: 2, active: false })).toEqual({ page: 2, page_size: USERS_PAGE_SIZE, q: 'ana', active: false })
    expect(buildUsersQuery({ search: '', page: 1, active: true })).toMatchObject({ active: true })
  })
})
