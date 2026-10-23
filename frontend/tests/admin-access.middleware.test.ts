import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RouteLocationNormalized } from 'vue-router'
import { signInWith } from './helpers/session'
import middleware from '../app/middleware/admin-access.global'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn((to: unknown) => to) }))
mockNuxtImport('navigateTo', () => navigateToMock)

const route = (path: string, leo?: Record<string, unknown>) =>
  ({ fullPath: path, path, meta: leo === undefined ? {} : { leo } }) as unknown as RouteLocationNormalized
const run = (to: RouteLocationNormalized) => middleware(to, to)

// Rutas administrativas (una por layer protegida + la raíz).
const ADMIN: [string, string][] = [
  ['/', 'inicio'],
  ['/users', 'users'],
  ['/users/abc', 'users detalle'],
  ['/roles', 'roles'],
  ['/roles/1', 'roles detalle'],
  ['/applications', 'applications'],
  ['/applications/1', 'applications detalle'],
  ['/audit', 'audit'],
  ['/sessions', 'sessions'],
  ['/ajustes', 'ajustes']
]

beforeEach(() => navigateToMock.mockClear())

describe('guardia admin-access (usuario sin leo.*, solo tags de otra app)', () => {
  beforeEach(() => signInWith(['acuarius.paciente.view']))

  it.each(ADMIN)('%s (%s): redirige a /sin-acceso', async (path) => {
    await run(route(path, { tag: 'leo.x.view' }))
    expect(navigateToMock).toHaveBeenCalledWith('/sin-acceso', { replace: true })
  })

  it.each([['/profile'], ['/sin-acceso'], ['/leo/forbidden']])('%s: pasa', async (path) => {
    expect(await run(route(path, {}))).toBeUndefined()
    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('rutas públicas (login, authorize, callback) pasan', async () => {
    expect(await run(route('/login', { public: true }))).toBeUndefined()
    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('sin permisos en absoluto: igual a /sin-acceso', async () => {
    signInWith([])
    await run(route('/'))
    expect(navigateToMock).toHaveBeenCalledWith('/sin-acceso', { replace: true })
  })
})

describe('guardia admin-access (administrador)', () => {
  it.each(ADMIN)('%s (%s): entra', async (path) => {
    signInWith(['leo.users.view'])
    expect(await run(route(path, { tag: 'leo.users.view' }))).toBeUndefined()
    expect(navigateToMock).not.toHaveBeenCalled()
  })
})

describe('guardia admin-access (sin sesión)', () => {
  it('no decide: lo hace leo-client', async () => {
    useState('leo-session').value = { status: 'anonymous', me: null }
    expect(await run(route('/users'))).toBeUndefined()
    expect(navigateToMock).not.toHaveBeenCalled()
  })
})
