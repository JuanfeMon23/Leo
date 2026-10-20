import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_USERS_TAGS, signInWith } from '../../../../tests/helpers/session'
import UsersRoleAssigner from './UsersRoleAssigner.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const options = [{ value: 'r1', label: 'Leo → Administrador' }, { value: 'r2', label: 'Taurus → Cajero' }]

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_USERS_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

const mountIt = (opts = options) => mountSuspended(UsersRoleAssigner, { props: { userId: 'u2', options: opts }, attachTo: document.body })

describe('UsersRoleAssigner', () => {
  it('ofrece «Aplicación → Rol» y el botón empieza deshabilitado', async () => {
    const wrapper = await mountIt()
    expect([...wrapper.get('select').element.querySelectorAll('option')].map(o => o.textContent?.trim())).toEqual(['Aplicación → Rol', 'Leo → Administrador', 'Taurus → Cajero'])
    expect(wrapper.get('[data-testid="role-assign"]').attributes('disabled')).toBeDefined()
  })

  it('asigna el rol elegido: POST /users/{id}/roles con role_ids y emite el detalle', async () => {
    const detail = { id: 'u2', roles: [] }
    api.mockResolvedValue(detail)
    const wrapper = await mountIt()
    await wrapper.get('select').setValue('r2')
    await wrapper.get('[data-testid="role-assign"]').trigger('click')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/users/u2/roles', { method: 'POST', body: { role_ids: ['r2'] } })
    expect(wrapper.emitted('assigned')?.[0]).toEqual([detail])
  })

  it('error del backend: mensaje legible y no emite', async () => {
    api.mockRejectedValue(new LeoApiError(422, 'invalid_reference', 'x'))
    const wrapper = await mountIt()
    await wrapper.get('select').setValue('r1')
    await wrapper.get('[data-testid="role-assign"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="assign-error"]').text()).toMatch(/rol/i)
    expect(wrapper.emitted('assigned')).toBeUndefined()
  })

  it('sin roles disponibles: selector deshabilitado con aviso', async () => {
    const wrapper = await mountIt([])
    expect(wrapper.get('select').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('No hay más roles activos')
  })
})
