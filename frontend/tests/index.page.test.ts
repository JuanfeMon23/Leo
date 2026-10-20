import { enableAutoUnmount } from '@vue/test-utils'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import { afterEach, describe, expect, it } from 'vitest'
import IndexPage from '../app/pages/index.vue'

enableAutoUnmount(afterEach)

describe('página de inicio', () => {
  it('da la bienvenida con el nombre del usuario', async () => {
    useState('leo-session').value = {
      status: 'authenticated',
      me: {
        user: { id: 'u1', username: 'ana', email: 'a@x.co', first_name: 'Ana', last_name: 'Pérez' },
        session: { id: 's', expires_at: '', last_activity_at: '', idle_timeout_seconds: 0 },
        permissions: [],
        applications: []
      }
    }
    const wrapper = await mountSuspended(IndexPage)
    expect(wrapper.get('[data-testid="welcome"]').text()).toBe('Bienvenido, Ana Pérez.')
  })
})
