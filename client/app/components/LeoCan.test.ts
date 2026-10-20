import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import LeoCan from './LeoCan.vue'
import { useCan } from '../composables/useCan'

enableAutoUnmount(afterEach)

function signIn(permissions: string[]) {
  useState('leo-session').value = {
    status: 'authenticated',
    me: {
      user: { id: 'u1', username: 'ana', email: 'ana@x.co', first_name: 'Ana', last_name: 'Pérez' },
      session: { id: 's1', expires_at: '', last_activity_at: '', idle_timeout_seconds: 0 },
      permissions,
      applications: []
    }
  }
}

const slots = {
  default: () => h('button', { 'data-testid': 'protected' }, 'Crear'),
  fallback: () => h('span', { 'data-testid': 'fallback' }, 'Sin permiso')
}

beforeEach(() => signIn(['leo.users.view', 'leo.users.create']))

describe('<LeoCan>', () => {
  it('renderiza el contenido si tiene el tag', async () => {
    const wrapper = await mountSuspended(LeoCan, { props: { tag: 'leo.users.create' }, slots })
    expect(wrapper.find('[data-testid="protected"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="fallback"]').exists()).toBe(false)
  })

  it('sin el tag NO renderiza el contenido (no está en el DOM) y muestra el fallback', async () => {
    const wrapper = await mountSuspended(LeoCan, { props: { tag: 'leo.users.deactivate' }, slots })
    expect(wrapper.html()).not.toContain('Crear')
    expect(wrapper.find('[data-testid="fallback"]').exists()).toBe(true)
  })

  it('varios tags: all por defecto, any con la prop any', async () => {
    const all = await mountSuspended(LeoCan, { props: { tag: ['leo.users.view', 'leo.audit.view'] }, slots })
    expect(all.find('[data-testid="protected"]').exists()).toBe(false)
    const any = await mountSuspended(LeoCan, { props: { tag: ['leo.users.view', 'leo.audit.view'], any: true }, slots })
    expect(any.find('[data-testid="protected"]').exists()).toBe(true)
  })

  it('reacciona al cambio de permisos (p. ej. al recargar la sesión)', async () => {
    const wrapper = await mountSuspended(LeoCan, { props: { tag: 'leo.audit.view' }, slots })
    expect(wrapper.find('[data-testid="protected"]').exists()).toBe(false)
    signIn(['leo.audit.view'])
    await nextTick()
    expect(wrapper.find('[data-testid="protected"]').exists()).toBe(true)
  })

  it('sin sesión no renderiza nada protegido', async () => {
    useState('leo-session').value = { status: 'anonymous', me: null }
    const wrapper = await mountSuspended(LeoCan, { props: { tag: 'leo.users.view' }, slots: { default: slots.default } })
    expect(wrapper.find('[data-testid="protected"]').exists()).toBe(false)
  })
})

describe('useCan', () => {
  it('es reactivo y acepta refs y modo any', () => {
    const tag = ref('leo.users.view')
    const can = useCan(tag)
    expect(can.value).toBe(true)
    tag.value = 'leo.roles.view'
    expect(can.value).toBe(false)
    expect(useCan(['leo.roles.view', 'leo.users.create'], 'any').value).toBe(true)
  })
})
