import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import LeoTopBar from './LeoTopBar.vue'

enableAutoUnmount(afterEach)

beforeEach(() => {
  useState('leo-session').value = {
    status: 'authenticated',
    me: {
      user: { id: 'u1', username: 'ana', email: 'ana@x.co', first_name: 'Ana', last_name: 'Pérez' },
      session: { id: 's1', expires_at: '', last_activity_at: '', idle_timeout_seconds: 0 },
      permissions: [],
      applications: [
        { slug: 'leo', name: 'Leo', base_url: 'http://localhost:3100' },
        { slug: 'vladimir', name: 'Vladimir', base_url: 'http://localhost:3200' }
      ]
    }
  }
})

describe('LeoTopBar', () => {
  it('muestra la app actual (por appSlug) y el usuario', async () => {
    const wrapper = await mountSuspended(LeoTopBar)
    expect(wrapper.get('[data-testid="leo-current-app"]').text()).toBe('Leo')
    expect(wrapper.get('[data-testid="leo-user-name"]').text()).toBe('Ana Pérez')
    expect(wrapper.text()).toContain('Cerrar sesión')
  })

  it('el selector lista las apps con acceso y marca la actual', async () => {
    const wrapper = await mountSuspended(LeoTopBar)
    const toggle = wrapper.get('button[aria-expanded]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    const links = wrapper.findAll('a')
    expect(links.map(a => a.text().replace(/\s+/g, ''))).toEqual(['LeoActual', 'Vladimir'])
    expect(links[1]!.attributes('href')).toBe('http://localhost:3200')
    expect(links[0]!.attributes('aria-current')).toBe('page')
  })

  it('sin sesión no muestra usuario ni acciones', async () => {
    useState('leo-session').value = { status: 'anonymous', me: null }
    const wrapper = await mountSuspended(LeoTopBar)
    expect(wrapper.text()).not.toContain('Cerrar sesión')
  })
})
