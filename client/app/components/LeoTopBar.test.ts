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
    // Cada enlace lleva ahora un avatar con la inicial (aria-hidden): se compara el nombre y la marca "Actual" por separado.
    expect(links.map(a => a.get('[data-testid="leo-app-name"]').text())).toEqual(['Leo', 'Vladimir'])
    expect(links[0]!.text()).toContain('Actual')
    expect(links[1]!.text()).not.toContain('Actual')
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

describe('LeoTopBar: diseño y selector de aplicaciones', () => {
  it('renderiza su propio header completo (idéntico en todas las apps) con slots start y end', async () => {
    const wrapper = await mountSuspended(LeoTopBar, {
      slots: { start: '<button data-testid="hamb">menú</button>', end: '<span data-testid="extra">extra</span>' }
    })
    const header = wrapper.get('header[data-testid="leo-topbar"]')
    for (const cls of ['sticky', 'top-0', 'z-20', 'h-14', 'border-b', 'border-border']) expect(header.classes()).toContain(cls)
    const children = Array.from(header.element.children)
    // #start antes de la marca de la app; #end dentro del grupo derecho.
    expect(children[0]!.getAttribute('data-testid')).toBe('hamb')
    expect(header.find('[data-testid="extra"]').exists()).toBe(true)
  })

  it('el slot end se muestra también sin sesión', async () => {
    useState('leo-session').value = { status: 'anonymous', me: null }
    const wrapper = await mountSuspended(LeoTopBar, { slots: { end: '<span data-testid="extra">extra</span>' } })
    expect(wrapper.find('[data-testid="extra"]').exists()).toBe(true)
  })

  it('el selector es un desplegable accesible: aria-controls, Esc lo cierra y devuelve el foco', async () => {
    const wrapper = await mountSuspended(LeoTopBar, { attachTo: document.body })
    const toggle = wrapper.get('[data-testid="leo-apps-button"]')
    await toggle.trigger('click')
    const panel = wrapper.get('[aria-label="Aplicaciones a las que tienes acceso"]')
    expect(toggle.attributes('aria-controls')).toBe(panel.attributes('id'))
    expect(toggle.attributes('aria-expanded')).toBe('true')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(wrapper.find('[aria-label="Aplicaciones a las que tienes acceso"]').exists()).toBe(false)
    expect(document.activeElement).toBe(toggle.element)
  })

  it('abrir un menú cierra el otro', async () => {
    const wrapper = await mountSuspended(LeoTopBar, { attachTo: document.body })
    await wrapper.get('[data-testid="leo-apps-button"]').trigger('click')
    await wrapper.get('[data-testid="leo-user-button"]').trigger('click')
    expect(wrapper.find('[aria-label="Aplicaciones a las que tienes acceso"]').exists()).toBe(false)
    expect(wrapper.find('[role="menu"]').exists()).toBe(true)
    await wrapper.get('[data-testid="leo-apps-button"]').trigger('click')
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
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

  it('"Cerrar sesión" va en rojo (variante danger de Andromeda) y "Mi perfil" no', async () => {
    const wrapper = await mountSuspended(LeoTopBar)
    await open(wrapper)
    const [profile, logout] = wrapper.findAll('[role="menuitem"]')
    expect(logout!.classes()).toContain('text-danger-600')
    expect(logout!.classes()).toContain('hover:bg-danger-50')
    expect(profile!.classes()).not.toContain('text-danger-600')
  })

  it('el panel separa tarjeta, "Mi perfil" y "Cerrar sesión" con separadores', async () => {
    const wrapper = await mountSuspended(LeoTopBar)
    await open(wrapper)
    expect(wrapper.findAll('[role="menu"] [role="separator"]')).toHaveLength(2)
  })

  it('las flechas, Inicio y Fin recorren los ítems del menú', async () => {
    const wrapper = await mountSuspended(LeoTopBar, { attachTo: document.body })
    await open(wrapper)
    await nextTick()
    const items = wrapper.findAll('[role="menuitem"]')
    const menu = wrapper.get('[role="menu"]')
    await menu.trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[1]!.element)
    await menu.trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[0]!.element)
    await menu.trigger('keydown', { key: 'End' })
    expect(document.activeElement).toBe(items[1]!.element)
    await menu.trigger('keydown', { key: 'Home' })
    expect(document.activeElement).toBe(items[0]!.element)
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
