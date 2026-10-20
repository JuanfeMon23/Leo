import { describe, expect, it } from 'vitest'
import { SESSIONS_PAGE_SIZE, buildSessionsQuery } from './sessionQuery'

describe('buildSessionsQuery', () => {
  it('sin usuario: solo activas por defecto, página y tamaño', () => {
    expect(buildSessionsQuery({ userId: '', activeOnly: true, page: 1 })).toEqual({ page: 1, page_size: SESSIONS_PAGE_SIZE, active_only: true })
  })

  it('envía active_only=false de forma explícita (el backend lo pone en true por defecto)', () => {
    expect(buildSessionsQuery({ userId: '', activeOnly: false, page: 2 })).toEqual({ page: 2, page_size: SESSIONS_PAGE_SIZE, active_only: false })
  })

  it('con usuario añade user_id', () => {
    expect(buildSessionsQuery({ userId: 'u1', activeOnly: true, page: 1 })).toMatchObject({ user_id: 'u1' })
  })
})
