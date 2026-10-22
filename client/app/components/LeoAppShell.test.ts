import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { signInWith } from '#leo-client/testing/session'
import LeoAppShell from './LeoAppShell.vue'

enableAutoUnmount(afterEach)

const items = [{ label: 'Inicio', to: '/', icon: 'home' }]

beforeEach(() => signInWith([]))

describe('LeoAppShell', () => {
  it('monta LeoTopBar con hamburguesa lg:hidden y el contenido', async () => {
    const wrapper = await mountSuspended(LeoAppShell, {
      props: { items, brand: 'Leo' },
      slots: { default: '<p data-testid="page">Hola</p>', 'sidebar-footer': '<span data-testid="foot">pie</span>' }
    })
    expect(wrapper.find('[data-testid="leo-topbar"]').exists()).toBe(true)
    const burger = wrapper.get('[aria-label="Abrir menú"]')
    expect(burger.classes()).toContain('lg:hidden')
    expect(wrapper.get('[data-testid="page"]').text()).toBe('Hola')
    expect(wrapper.find('[data-testid="foot"]').exists()).toBe(true)
  })

  it('la hamburguesa abre el cajón del menú', async () => {
    const wrapper = await mountSuspended(LeoAppShell, { props: { items, brand: 'Leo' } })
    const before = wrapper.html()
    await wrapper.get('[aria-label="Abrir menú"]').trigger('click')
    expect(wrapper.html()).not.toBe(before)
  })
})
