import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import UiPasswordRequirements from './UiPasswordRequirements.vue'

enableAutoUnmount(afterEach)

const met = (wrapper: Awaited<ReturnType<typeof mountSuspended>>) =>
  wrapper.findAll('[data-testid="password-requirement"]').map((li: { attributes: (n: string) => string | undefined }) => li.attributes('data-met'))

describe('UiPasswordRequirements', () => {
  it('con la contraseña vacía solo cumple «no contiene el usuario»', async () => {
    const wrapper = await mountSuspended(UiPasswordRequirements, { props: { password: '' } })
    expect(met(wrapper)).toEqual(['false', 'false', 'false', 'false', 'false', 'true'])
  })

  it('se actualiza en vivo al cambiar la contraseña', async () => {
    const wrapper = await mountSuspended(UiPasswordRequirements, { props: { password: 'abc' } })
    expect(met(wrapper)).toEqual(['false', 'true', 'false', 'false', 'false', 'true'])
    await wrapper.setProps({ password: 'Segura-Clave-2026' })
    expect(met(wrapper)).toEqual(['true', 'true', 'true', 'true', 'true', 'true'])
  })

  it('marca como no cumplido el requisito si contiene el usuario', async () => {
    const wrapper = await mountSuspended(UiPasswordRequirements, { props: { password: 'Hola-ana.perez-2026', username: 'ana.perez' } })
    expect(met(wrapper).at(-1)).toBe('false')
  })

  it('nunca muestra la contraseña', async () => {
    const wrapper = await mountSuspended(UiPasswordRequirements, { props: { password: 'Segura-Clave-2026' } })
    expect(wrapper.html()).not.toContain('Segura-Clave-2026')
  })
})
