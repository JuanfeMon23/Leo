import { describe, expect, it } from 'vitest'
import { isProtectedApp, previewActionTag } from './actionTag'

describe('previewActionTag', () => {
  it('arma <app>.<modulo>.<verbo>', () => {
    expect(previewActionTag('vladimir', 'samples', 'edit')).toEqual({ text: 'vladimir.samples.edit', complete: true })
  })

  it('sin verbo muestra el marcador y no está completo', () => {
    expect(previewActionTag('leo', 'users', '')).toEqual({ text: 'leo.users.‹verbo›', complete: false })
    expect(previewActionTag('leo', 'users', '   ')).toEqual({ text: 'leo.users.‹verbo›', complete: false })
  })

  it('recorta espacios del verbo', () => {
    expect(previewActionTag('leo', 'users', ' rotate-secret ')).toEqual({ text: 'leo.users.rotate-secret', complete: true })
  })

  it('un verbo que no es kebab-case no está completo', () => {
    expect(previewActionTag('leo', 'users', 'Edit').complete).toBe(false)
    expect(previewActionTag('leo', 'users', 'a b').complete).toBe(false)
    expect(previewActionTag('leo', 'users', 'a.b').complete).toBe(false)
    expect(previewActionTag('leo', 'users', '-x').complete).toBe(false)
  })
})

describe('isProtectedApp', () => {
  it('solo la app leo es protegida', () => {
    expect(isProtectedApp('leo')).toBe(true)
    expect(isProtectedApp('vladimir')).toBe(false)
  })
})
