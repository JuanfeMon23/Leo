import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RouteLocationNormalized } from 'vue-router'
import { loginLoopGuard } from '../lib/loginGuard'
import middleware from './leo.global'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn((to: unknown) => to) }))
mockNuxtImport('navigateTo', () => navigateToMock)

function route(fullPath: string, leo?: Record<string, unknown>) {
  const path = fullPath.split('?')[0]!
  return { fullPath, path, meta: leo === undefined ? {} : { leo } } as unknown as RouteLocationNormalized
}

function session(status: 'authenticated' | 'anonymous', permissions: string[] = []) {
  useState('leo-session').value = {
    status,
    me: status === 'anonymous'
      ? null
      : {
          user: { id: 'u1', username: 'ana', email: 'a@x.co', first_name: 'Ana', last_name: 'P' },
          session: { id: 's', expires_at: '', last_activity_at: '', idle_timeout_seconds: 0 },
          permissions,
          applications: []
        }
  }
}

const run = (to: RouteLocationNormalized) => middleware(to, to)

beforeEach(() => {
  navigateToMock.mockClear()
  loginLoopGuard.reset()
})

describe('middleware leo.global: tope de bucles de login', () => {
  it('tras 2 redirecciones en la ventana aborta con 401 y mensaje fijo; me() ok reinicia', async () => {
    loginLoopGuard.reset()
    session('anonymous')
    await run(route('/a', { tag: 'x' }))
    await run(route('/a', { tag: 'x' }))
    navigateToMock.mockClear()
    const blocked = await run(route('/a', { tag: 'x' })).catch((e: unknown) => e)
    expect(navigateToMock).not.toHaveBeenCalled()
    expect(blocked).toMatchObject({ statusCode: 401, statusMessage: 'No pudimos iniciar tu sesión. Cierra la pestaña e inténtalo de nuevo.' })
    loginLoopGuard.reset()
    await run(route('/a', { tag: 'x' }))
    expect(navigateToMock).toHaveBeenCalledTimes(1)
  })
})

describe('middleware leo.global', () => {
  it('página pública: pasa sin sesión', async () => {
    session('anonymous')
    expect(await run(route('/login', { public: true }))).toBeUndefined()
    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('sin sesión: va al login conservando a dónde volver', async () => {
    session('anonymous')
    await run(route('/users?page=2', { tag: 'leo.users.view' }))
    expect(navigateToMock).toHaveBeenCalledWith('/login?redirect=%2Fusers%3Fpage%3D2', { external: false, replace: true })
  })

  it('con sesión y el tag: pasa', async () => {
    session('authenticated', ['leo.users.view'])
    expect(await run(route('/users', { tag: 'leo.users.view' }))).toBeUndefined()
    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('con sesión pero sin el tag: página 403', async () => {
    session('authenticated', ['leo.users.view'])
    await run(route('/audit', { tag: 'leo.audit.view' }))
    expect(navigateToMock).toHaveBeenCalledWith({ path: '/leo/forbidden', query: { from: '/audit' } }, { replace: true })
  })

  it('varios tags con mode any', async () => {
    session('authenticated', ['leo.audit.export'])
    expect(await run(route('/audit', { tag: ['leo.audit.view', 'leo.audit.export'], mode: 'any' }))).toBeUndefined()
    await run(route('/audit', { tag: ['leo.audit.view', 'leo.audit.export'] }))
    expect(navigateToMock).toHaveBeenCalledTimes(1)
  })

  it('página sin meta leo: exige sesión pero no tag', async () => {
    session('authenticated', [])
    expect(await run(route('/'))).toBeUndefined()
  })
})
