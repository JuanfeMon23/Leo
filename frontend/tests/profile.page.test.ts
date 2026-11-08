import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import ProfilePage from '../layers/profile/app/pages/profile/index.vue'
import { signInWith } from './helpers/session'

enableAutoUnmount(afterEach)

beforeEach(() => signInWith([])) // sin ningún tag: es autogestión

describe('página /profile', () => {
  it('«Mi perfil» se muestra a quien solo tiene sesión (sin tags)', async () => {
    const wrapper = await mountSuspended(ProfilePage)
    expect(wrapper.text()).toContain('Mi perfil')
    expect(wrapper.find('[data-testid="profile-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="password-form"]').exists()).toBe(true)
  })

  it('sin ?return= válido no hay enlace de vuelta', async () => {
    const wrapper = await mountSuspended(ProfilePage)
    expect(wrapper.find('[data-testid="profile-return"]').exists()).toBe(false)
  })
})
