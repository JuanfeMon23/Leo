import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DefaultLayout from '../app/layouts/default.vue'
import UsersIndexPage from '../layers/users/app/pages/users/index.vue'
import { signInWith } from './helpers/session'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

beforeEach(() => {
  api.mockReset()
  api.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
})
afterEach(() => { document.body.innerHTML = '' })

describe('rutas de usuarios', () => {
  it('el listado y el detalle exigen leo.users.view', () => {
    const router = useRouter()
    expect(router.resolve('/users').meta.leo?.tag).toBe('leo.users.view')
    expect(router.resolve('/users/abc').meta.leo?.tag).toBe('leo.users.view')
  })

  it('la página del listado se renderiza', async () => {
    signInWith(['leo.users.view'])
    const wrapper = await mountSuspended(UsersIndexPage)
    await flushPromises()
    expect(wrapper.text()).toContain('Usuarios')
  })
})

describe('menú lateral: Usuarios', () => {
  it('aparece con leo.users.view', async () => {
    signInWith(['leo.users.view'])
    const wrapper = await mountSuspended(DefaultLayout)
    const link = wrapper.findAll('a').find(a => a.text().includes('Usuarios'))
    expect(link?.attributes('href')).toBe('/users')
  })

  it('no aparece sin ese tag', async () => {
    signInWith(['leo.roles.view'])
    const wrapper = await mountSuspended(DefaultLayout)
    expect(wrapper.findAll('a').some(a => a.text().includes('Usuarios'))).toBe(false)
  })
})
