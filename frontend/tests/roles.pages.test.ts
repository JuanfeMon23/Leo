import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DefaultLayout from '../app/layouts/default.vue'
import RolesIndexPage from '../layers/roles/app/pages/roles/index.vue'
import { signInWith } from './helpers/session'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

beforeEach(() => {
  api.mockReset()
  api.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
})
afterEach(() => { document.body.innerHTML = '' })

describe('rutas de roles', () => {
  it('el listado y el detalle exigen leo.roles.view', () => {
    const router = useRouter()
    expect(router.resolve('/roles').meta.leo?.tag).toBe('leo.roles.view')
    expect(router.resolve('/roles/abc').meta.leo?.tag).toBe('leo.roles.view')
  })

  it('la página del listado se renderiza', async () => {
    signInWith(['leo.roles.view'])
    const wrapper = await mountSuspended(RolesIndexPage)
    await flushPromises()
    expect(wrapper.text()).toContain('Roles')
  })
})

describe('menú lateral: Roles', () => {
  it('aparece con leo.roles.view', async () => {
    signInWith(['leo.roles.view'])
    const wrapper = await mountSuspended(DefaultLayout)
    const link = wrapper.findAll('a').find(a => a.text().includes('Roles'))
    expect(link?.attributes('href')).toBe('/roles')
  })

  it('no aparece sin ese tag', async () => {
    signInWith(['leo.applications.view'])
    const wrapper = await mountSuspended(DefaultLayout)
    expect(wrapper.findAll('a').some(a => a.text().includes('Roles'))).toBe(false)
  })
})
