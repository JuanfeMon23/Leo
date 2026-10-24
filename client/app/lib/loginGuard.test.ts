import { describe, expect, it } from 'vitest'
import { createLoginLoopGuard } from './loginGuard'

function fake() {
  const data = new Map<string, string>()
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k)
  }
}

describe('createLoginLoopGuard', () => {
  it('permite 2 redirecciones por ventana y bloquea la tercera', () => {
    const guard = createLoginLoopGuard({ storage: fake, now: () => 1000 })
    expect([guard.attempt(), guard.attempt(), guard.attempt(), guard.attempt()]).toEqual([true, true, false, false])
  })

  it('la ventana de 30 s expira los intentos viejos', () => {
    let t = 0
    const store = fake()
    const guard = createLoginLoopGuard({ storage: () => store, now: () => t })
    guard.attempt()
    t = 10_000
    guard.attempt()
    t = 20_000
    expect(guard.attempt()).toBe(false)
    t = 30_001 // el primero salió de la ventana
    expect(guard.attempt()).toBe(true)
  })

  it('reset reinicia el contador', () => {
    const guard = createLoginLoopGuard({ storage: fake, now: () => 1 })
    guard.attempt()
    guard.attempt()
    guard.reset()
    expect(guard.attempt()).toBe(true)
  })

  it('persiste entre instancias (recarga de página) vía storage', () => {
    const store = fake()
    createLoginLoopGuard({ storage: () => store, now: () => 1 }).attempt()
    createLoginLoopGuard({ storage: () => store, now: () => 2 }).attempt()
    expect(createLoginLoopGuard({ storage: () => store, now: () => 3 }).attempt()).toBe(false)
  })

  it('sin storage (null o que lanza) cuenta en memoria', () => {
    for (const storage of [() => null, () => { throw new Error('denied') }]) {
      const guard = createLoginLoopGuard({ storage, now: () => 1 })
      expect([guard.attempt(), guard.attempt(), guard.attempt()]).toEqual([true, true, false])
    }
  })

  it('storage corrupto se ignora', () => {
    const store = fake()
    store.setItem('leo:login-attempts', '{no json')
    expect(createLoginLoopGuard({ storage: () => store, now: () => 1 }).attempt()).toBe(true)
  })
})
