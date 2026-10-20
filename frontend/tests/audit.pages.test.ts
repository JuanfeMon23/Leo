import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DefaultLayout from '../app/layouts/default.vue'
import AuditIndexPage from '../layers/audit/app/pages/audit/index.vue'
import SessionsIndexPage from '../layers/sessions/app/pages/sessions/index.vue'
import { signInWith } from './helpers/session'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

beforeEach(() => {
  api.mockReset()
  api.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
})
afterEach(() => { document.body.innerHTML = '' })

describe('rutas de auditoría y sesiones', () => {
  it('/audit exige leo.audit.view y /sessions exige leo.auth.view', () => {
    const router = useRouter()
    expect(router.resolve('/audit').meta.leo?.tag).toBe('leo.audit.view')
    expect(router.resolve('/sessions').meta.leo?.tag).toBe('leo.auth.view')
  })

  it('las páginas se renderizan', async () => {
    signInWith(['leo.audit.view', 'leo.auth.view'])
    const audit = await mountSuspended(AuditIndexPage)
    await flushPromises()
    expect(audit.text()).toContain('Auditoría')
    const sessions = await mountSuspended(SessionsIndexPage)
    await flushPromises()
    expect(sessions.text()).toContain('Sesiones')
  })
})

describe('menú lateral: Auditoría y Sesiones', () => {
  it('aparecen con sus tags de consulta', async () => {
    signInWith(['leo.audit.view', 'leo.auth.view'])
    const wrapper = await mountSuspended(DefaultLayout)
    expect(wrapper.findAll('a').find(a => a.text().includes('Auditoría'))?.attributes('href')).toBe('/audit')
    expect(wrapper.findAll('a').find(a => a.text().includes('Sesiones'))?.attributes('href')).toBe('/sessions')
  })

  it('no aparecen sin esos tags', async () => {
    signInWith(['leo.applications.view'])
    const wrapper = await mountSuspended(DefaultLayout)
    expect(wrapper.findAll('a').some(a => a.text().includes('Auditoría'))).toBe(false)
    expect(wrapper.findAll('a').some(a => a.text().includes('Sesiones'))).toBe(false)
  })
})
