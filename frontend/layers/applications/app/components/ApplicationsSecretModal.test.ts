import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ApplicationsSecretModal from './ApplicationsSecretModal.vue'

enableAutoUnmount(afterEach)

const reveal = { clientId: 'vladimir', secret: 'S3cr3t-de-prueba', reason: 'created' as const }
const dialog = () => document.body.querySelector<HTMLElement>('[role="dialog"]')
const byId = (id: string) => document.body.querySelector<HTMLElement>(`[data-testid="${id}"]`)

afterEach(() => {
  document.body.innerHTML = ''
  document.body.style.overflow = ''
  vi.unstubAllGlobals()
})

describe('ApplicationsSecretModal', () => {
  it('sin secreto no renderiza nada', async () => {
    await mountSuspended(ApplicationsSecretModal, { props: { reveal: null }, attachTo: document.body })
    expect(dialog()).toBeNull()
  })

  it('muestra client_id, secreto y la advertencia de que es de un solo uso', async () => {
    await mountSuspended(ApplicationsSecretModal, { props: { reveal }, attachTo: document.body })
    expect(byId('secret-value')!.textContent).toBe('S3cr3t-de-prueba')
    expect(byId('secret-client-id')!.textContent).toBe('vladimir')
    expect(dialog()!.textContent).toContain('No volverá a mostrarse')
  })

  it('rotado: avisa que el secreto anterior dejó de funcionar', async () => {
    await mountSuspended(ApplicationsSecretModal, { props: { reveal: { ...reveal, reason: 'rotated' } }, attachTo: document.body })
    expect(dialog()!.textContent).toContain('el anterior ya dejó de funcionar')
  })

  it('Copiar escribe el secreto en el portapapeles', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    await mountSuspended(ApplicationsSecretModal, { props: { reveal }, attachTo: document.body })
    byId('secret-copy')!.click()
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('S3cr3t-de-prueba')
    expect(byId('secret-copy')!.textContent).toContain('Copiado')
  })

  it('si el portapapeles falla, lo dice de forma legible', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('NotAllowedError')) } })
    await mountSuspended(ApplicationsSecretModal, { props: { reveal }, attachTo: document.body })
    byId('secret-copy')!.click()
    await flushPromises()
    expect(byId('secret-copy-error')!.textContent).toContain('No se pudo copiar')
    expect(byId('secret-copy-error')!.textContent).not.toContain('NotAllowedError')
  })

  it('no se cierra con Esc: solo con el botón explícito, que emite close', async () => {
    const wrapper = await mountSuspended(ApplicationsSecretModal, { props: { reveal }, attachTo: document.body })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(wrapper.emitted('close')).toBeUndefined()
    byId('secret-done')!.click()
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('no deja el secreto en el almacenamiento del navegador', async () => {
    await mountSuspended(ApplicationsSecretModal, { props: { reveal }, attachTo: document.body })
    const dump = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage })
    expect(dump).not.toContain('S3cr3t-de-prueba')
  })
})
