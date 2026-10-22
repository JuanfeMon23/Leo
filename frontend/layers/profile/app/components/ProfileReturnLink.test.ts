import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { signInWith } from '../../../../tests/helpers/session'
import ProfileReturnLink from './ProfileReturnLink.vue'

enableAutoUnmount(afterEach)

beforeEach(() => {
  signInWith([])
  const state = useState<{ me: { applications: unknown[] } }>('leo-session')
  state.value.me.applications = [{ slug: 'vladimir', name: 'Vladimir', base_url: 'https://vladimir.example.co' }]
})

describe('ProfileReturnLink', () => {
  it('con una URL del origen de una app: «Volver a <app>»', async () => {
    const w = await mountSuspended(ProfileReturnLink, { props: { returnParam: 'https://vladimir.example.co/samples' } })
    const a = w.get('[data-testid="profile-return"]')
    expect(a.text()).toContain('Volver a Vladimir')
    expect(a.attributes('href')).toBe('https://vladimir.example.co/samples')
  })

  it.each([
    'javascript:alert(1)',
    'https://evil.example/x',
    '//evil.example',
    '/users',
    ''
  ])('no muestra enlace para «%s»', async (returnParam) => {
    const w = await mountSuspended(ProfileReturnLink, { props: { returnParam } })
    expect(w.find('[data-testid="profile-return"]').exists()).toBe(false)
  })

  it('sin parámetro no muestra enlace', async () => {
    const w = await mountSuspended(ProfileReturnLink)
    expect(w.find('a').exists()).toBe(false)
  })
})
