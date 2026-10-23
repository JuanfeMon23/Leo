import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { signInWith } from './helpers/session'
import NoAccessPage from '../app/pages/sin-acceso.vue'

enableAutoUnmount(afterEach)

describe('página «Sin acceso al panel»', () => {
  it('solo ofrece «Mi perfil» y «Cerrar sesión», sin listar el panel', async () => {
    signInWith(['acuarius.paciente.view'])
    const w = await mountSuspended(NoAccessPage)
    expect(w.text()).toContain('Sin acceso al panel')
    expect(w.get('[data-testid="no-access-profile"]').attributes('href')).toBe('/profile')
    expect(w.get('[data-testid="no-access-logout"]').text()).toBe('Cerrar sesión')
    expect(w.findAll('a, button')).toHaveLength(2)
    expect(w.text()).not.toMatch(/usuarios|roles|aplicaciones|auditor/i)
  })
})
