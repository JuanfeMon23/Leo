import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LeoTopBar from './LeoTopBar.vue'

enableAutoUnmount(afterEach)

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn(async () => {}) }))
mockNuxtImport('navigateTo', () => navigateToMock)

const leoConfig = () => useRuntimeConfig().public.leo as { transport: string, leoUrl: string }

beforeEach(() => {
  leoConfig().transport = 'leo-direct'
  leoConfig().leoUrl = ''
  navigateToMock.mockClear()
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
    // "Cerrar sesión" vive ahora dentro del menú de usuario (cerrado por defecto).
    await wrapper.get('[data-testid="leo-user-button"]').trigger('click')
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
    expect(wrapper.find('[data-testid="leo-user-button"]').exists()).toBe(false)
  })
})

describe('LeoTopBar: menú de usuario', () => {
  const open = async (wrapper: Awaited<ReturnType<typeof mountSuspended>>) => {
    await wrapper.get('[data-testid="leo-user-button"]').trigger('click')
  }

  it('el botón muestra iniciales y tiene roles/aria de menú', async () => {
    const wrapper = await mountSuspended(LeoTopBar, { attachTo: document.body })
    const button = wrapper.get('[data-testid="leo-user-button"]')
    expect(wrapper.get('[data-testid="leo-user-initials"]').text()).toBe('AP')
    expect(button.attributes('aria-haspopup')).toBe('menu')
    expect(button.attributes('aria-expanded')).toBe('false')
    await open(wrapper)
    expect(button.attributes('aria-expanded')).toBe('true')
    expect(button.attributes('aria-controls')).toBe(wrapper.get('[role="menu"]').attributes('id'))
    expect(wrapper.findAll('[role="menuitem"]').map(i => i.text())).toEqual(['Mi perfil', 'Cerrar sesión'])
  })

  it('muestra nombre completo, correo y @usuario (solo lectura)', async () => {
    const wrapper = await mountSuspended(LeoTopBar)
    await open(wrapper)
    const card = wrapper.get('[data-testid="leo-user-card"]')
    expect(card.text()).toContain('Ana Pérez')
    expect(wrapper.get('[data-testid="leo-user-email"]').text()).toBe('ana@x.co')
    expect(wrapper.get('[data-testid="leo-user-username"]').text()).toBe('@ana')
    expect(card.findAll('input, button, a')).toHaveLength(0)
  })

  it('abre y cierra con clic en el botón y con Esc (devuelve el foco)', async () => {
    const wrapper = await mountSuspended(LeoTopBar, { attachTo: document.body })
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    await open(wrapper)
    expect(wrapper.find('[role="menu"]').exists()).toBe(true)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.get('[data-testid="leo-user-button"]').element)
    await open(wrapper)
    await open(wrapper)
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
  })

  it('cierra al hacer clic fuera y pone el foco en el primer elemento al abrir', async () => {
    const wrapper = await mountSuspended(LeoTopBar, { attachTo: document.body })
    await open(wrapper)
    await nextTick()
    expect(document.activeElement).toBe(wrapper.findAll('[role="menuitem"]')[0]!.element)
    document.body.click()
    await nextTick()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
  })

  it('direct: "Mi perfil" es un enlace interno a /profile', async () => {
    const wrapper = await mountSuspended(LeoTopBar)
    await open(wrapper)
    expect(wrapper.findAll('[role="menuitem"]')[0]!.attributes('href')).toBe('/profile')
  })

  it('bff: "Mi perfil" apunta a leoUrl con return codificado', async () => {
    leoConfig().transport = 'bff'
    leoConfig().leoUrl = 'http://localhost:3100'
    const wrapper = await mountSuspended(LeoTopBar)
    await open(wrapper)
    const href = wrapper.findAll('[role="menuitem"]')[0]!.attributes('href')!
    expect(href.startsWith('http://localhost:3100/profile?return=')).toBe(true)
    expect(decodeURIComponent(href.split('return=')[1]!)).toBe(globalThis.location.href.split('#')[0])
  })

  it('bff sin leoUrl: oculta "Mi perfil" y deja los datos y cerrar sesión', async () => {
    leoConfig().transport = 'bff'
    const wrapper = await mountSuspended(LeoTopBar)
    await open(wrapper)
    expect(wrapper.findAll('[role="menuitem"]').map(i => i.text())).toEqual(['Cerrar sesión'])
    expect(wrapper.get('[data-testid="leo-user-email"]').text()).toBe('ana@x.co')
  })

  it('cerrar sesión llama al transporte y navega al login', async () => {
    const { $leo } = useNuxtApp()
    const logout = vi.spyOn($leo.transport, 'logout').mockResolvedValue()
    const login = vi.spyOn($leo.transport, 'login').mockResolvedValue({ url: '/login', external: false })
    const wrapper = await mountSuspended(LeoTopBar)
    await open(wrapper)
    await wrapper.findAll('[role="menuitem"]')[1]!.trigger('click')
    await vi.waitFor(() => expect(navigateToMock).toHaveBeenCalled())
    expect(logout).toHaveBeenCalledTimes(1)
    expect(login).toHaveBeenCalled()
    logout.mockRestore()
    login.mockRestore()
  })

  it('sin nombre cae a username; sin datos solo hay "Cerrar sesión"', async () => {
    const me = (useState('leo-session').value as { me: { user: Record<string, string> } }).me
    me.user = { id: 'u2', username: 'bot', email: '', first_name: '', last_name: '' }
    const wrapper = await mountSuspended(LeoTopBar)
    expect(wrapper.get('[data-testid="leo-user-name"]').text()).toBe('bot')
    expect(wrapper.get('[data-testid="leo-user-initials"]').text()).toBe('B')
    await open(wrapper)
    expect(wrapper.find('[data-testid="leo-user-email"]').exists()).toBe(false)

    me.user = { id: 'u3', username: '', email: '', first_name: '', last_name: '' }
    await nextTick()
    expect(wrapper.find('[data-testid="leo-user-card"]').exists()).toBe(false)
    expect(wrapper.findAll('[role="menuitem"]').map(i => i.text())).toEqual(['Mi perfil', 'Cerrar sesión'])
  })
})
