import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import UiPasswordInput from '#andromeda/components/ui/UiPasswordInput.vue'

enableAutoUnmount(afterEach)

const toggle = (w: Awaited<ReturnType<typeof mountSuspended>>) => w.get('[data-testid="password-toggle"]')

describe('UiPasswordInput', () => {
  it('inicia oculta y el ojo alterna type, aria-pressed y aria-label', async () => {
    const w = await mountSuspended(UiPasswordInput, { props: { modelValue: 'abc' }, attrs: { autocomplete: 'new-password' } })
    expect(w.get('input').attributes('type')).toBe('password')
    expect(w.get('input').attributes('autocomplete')).toBe('new-password')
    expect(toggle(w).attributes('aria-pressed')).toBe('false')
    expect(toggle(w).attributes('aria-label')).toBe('Mostrar contraseña')
    await toggle(w).trigger('click')
    expect(w.get('input').attributes('type')).toBe('text')
    expect(toggle(w).attributes('aria-pressed')).toBe('true')
    expect(toggle(w).attributes('aria-label')).toBe('Ocultar contraseña')
    await toggle(w).trigger('click')
    expect(w.get('input').attributes('type')).toBe('password')
  })

  it('el botón es type=button y no envía el formulario; está a la izquierda del input', async () => {
    const onSubmit = vi.fn((e: Event) => e.preventDefault())
    const Host = defineComponent({
      render: () => h('form', { onSubmit }, [h(UiPasswordInput, { modelValue: 'x' })])
    })
    const w = await mountSuspended(Host)
    const btn = w.get('[data-testid="password-toggle"]')
    expect(btn.attributes('type')).toBe('button')
    expect(btn.classes()).toContain('left-0')
    expect(w.get('input').classes()).toContain('pl-10')
    await btn.trigger('click')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('propaga el estado inválido y disabled', async () => {
    const inv = await mountSuspended(UiPasswordInput, { props: { modelValue: '' }, attrs: { invalid: true } })
    expect(inv.get('input').attributes('aria-invalid')).toBe('true')
    expect(inv.get('input').classes()).toContain('bg-danger-50')
    const dis = await mountSuspended(UiPasswordInput, { props: { modelValue: '', disabled: true } })
    expect(dis.get('input').attributes('disabled')).toBeDefined()
    expect(toggle(dis).attributes('disabled')).toBeDefined()
  })

  it('vuelve a oculta al vaciarse el valor y al desmontar', async () => {
    const w = await mountSuspended(UiPasswordInput, { props: { modelValue: 'abc' } })
    await toggle(w).trigger('click')
    expect(w.get('input').attributes('type')).toBe('text')
    await w.setProps({ modelValue: '' })
    await nextTick()
    expect(w.get('input').attributes('type')).toBe('password')
    w.unmount()
    const again = await mountSuspended(UiPasswordInput, { props: { modelValue: 'abc' } })
    expect(again.get('input').attributes('type')).toBe('password')
  })
})
