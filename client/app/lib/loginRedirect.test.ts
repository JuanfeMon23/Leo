import { describe, expect, it, vi } from 'vitest'
import { createLoginLoopGuard } from './loginGuard'
import { createLoginRedirector } from './loginRedirect'

function setup(over: Partial<Parameters<typeof createLoginRedirector>[0]> = {}) {
  let path = '/a'
  const login = vi.fn(async (returnTo: string) => {
    await Promise.resolve()
    path = '/changed' // el estado cambia mientras se pide la URL
    return { url: `/login?redirect=${returnTo}`, external: false }
  })
  const navigate = vi.fn(async () => {})
  const onBlocked = vi.fn()
  const onError = vi.fn()
  const store = new Map<string, string>()
  const guard = createLoginLoopGuard({
    now: () => 1,
    storage: () => ({ getItem: k => store.get(k) ?? null, setItem: (k, v) => void store.set(k, v), removeItem: k => void store.delete(k) })
  })
  const redirect = createLoginRedirector({ skip: () => false, currentPath: () => path, login, navigate, guard, onBlocked, onError, ...over })
  return { redirect, login, navigate, onBlocked, onError, guard }
}

describe('createLoginRedirector', () => {
  it('N 401 simultáneos → una sola redirección con el returnTo del primero', async () => {
    const { redirect, login, navigate } = setup()
    await Promise.all(Array.from({ length: 5 }, () => redirect('expired')))
    expect(login).toHaveBeenCalledTimes(1)
    expect(login).toHaveBeenCalledWith('/a', 'expired')
    expect(navigate).toHaveBeenCalledTimes(1)
  })

  it('tras una redirección externa no vuelve a pedir login', async () => {
    const { redirect, login } = setup({
      login: vi.fn(async () => ({ url: 'https://leo/authorize', external: true }))
    })
    await redirect()
    await redirect()
    expect(login).not.toHaveBeenCalled()
  })

  it('tras una redirección interna se puede volver a pedir', async () => {
    const { redirect, login } = setup()
    await redirect()
    await redirect()
    expect(login).toHaveBeenCalledTimes(2)
  })

  it('al exceder 2 redirecciones por ventana no redirige y avisa', async () => {
    const { redirect, login, onBlocked } = setup()
    await redirect()
    await redirect()
    await redirect()
    expect(login).toHaveBeenCalledTimes(2)
    expect(onBlocked).toHaveBeenCalledTimes(1)
  })

  it('tras reset del guard (me() ok) vuelve a permitir', async () => {
    const { redirect, login, guard, onBlocked } = setup()
    await redirect()
    await redirect()
    guard.reset()
    await redirect()
    expect(login).toHaveBeenCalledTimes(3)
    expect(onBlocked).not.toHaveBeenCalled()
  })

  it('skip (ya en login/callback) no cuenta ni redirige', async () => {
    const { redirect, login, guard } = setup({ skip: () => true })
    await redirect()
    expect(login).not.toHaveBeenCalled()
    expect(guard.attempt()).toBe(true)
  })

  it('error al pedir login → onError y se libera para reintentar', async () => {
    const boom = new Error('x')
    const { redirect, onError } = setup({ login: vi.fn(async () => { throw boom }) })
    await redirect()
    expect(onError).toHaveBeenCalledWith(boom)
    await redirect()
    expect(onError).toHaveBeenCalledTimes(2)
  })
})
