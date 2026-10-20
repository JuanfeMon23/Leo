import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DefaultLayout from '../app/layouts/default.vue'
import ApplicationsIndexPage from '../layers/applications/app/pages/applications/index.vue'
import { signInWith } from './helpers/session'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

beforeEach(() => {
  api.mockReset()
  api.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
})
afterEach(() => { document.body.innerHTML = '' })

describe('rutas de applications', () => {
  it('el listado y el detalle exigen leo.applications.view', () => {
    const router = useRouter()
    expect(router.resolve('/applications').meta.leo?.tag).toBe('leo.applications.view')
    expect(router.resolve('/applications/abc').meta.leo?.tag).toBe('leo.applications.view')
  })

  it('la página del listado se renderiza', async () => {
    signInWith(['leo.applications.view'])
    const wrapper = await mountSuspended(ApplicationsIndexPage)
    await flushPromises()
    expect(wrapper.text()).toContain('Aplicaciones')
  })
})

describe('menú lateral', () => {
  it('muestra «Aplicaciones» con leo.applications.view', async () => {
    signInWith(['leo.applications.view'])
    const wrapper = await mountSuspended(DefaultLayout)
    const link = wrapper.findAll('a').find(a => a.text().includes('Aplicaciones'))
    expect(link?.attributes('href')).toBe('/applications')
  })

  it('no la muestra sin ese tag', async () => {
    signInWith(['leo.users.view'])
    const wrapper = await mountSuspended(DefaultLayout)
    expect(wrapper.findAll('a').some(a => a.text().includes('Aplicaciones'))).toBe(false)
  })
})
