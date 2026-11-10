import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { forbiddenMessage } from '#leo-client/lib/permissionNames'
import DefaultLayout from '../app/layouts/default.vue'
import { clearDocumentTypesCache } from '../app/composables/useDocumentTypes'
import DocumentTypesIndexPage from '../layers/document-types/app/pages/document-types/index.vue'
import { ALL_DOCUMENT_TYPES_TAGS, signInWith } from './helpers/session'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const documentType = (over: Record<string, unknown> = {}) => ({ code: 'CC', name: 'Cédula de ciudadanía', sort_order: 10, is_active: true, ...over })
const CATALOG = [documentType(), documentType({ code: 'OLD', name: 'Tipo antiguo', sort_order: 99, is_active: false })]

const byId = (id: string) => [...document.body.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`)]
const dialog = () => document.body.querySelector('[role="dialog"]')!
const dialogButton = (label: string) => [...dialog().querySelectorAll<HTMLButtonElement>('button')].find(button => button.textContent?.trim() === label)!
const dialogInputs = () => [...dialog().querySelectorAll<HTMLInputElement>('input')]
const submitDialog = () => dialog().querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit', { cancelable: true }))
async function typeInto(element: HTMLInputElement, value: string) {
  element.value = value
  element.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
async function mountPage() {
  const wrapper = await mountSuspended(DocumentTypesIndexPage, { attachTo: document.body })
  await flushPromises()
  return wrapper
}
async function fillCreateForm(code: string, name: string, order: string) {
  byId('document-type-create')[0]!.click()
  await flushPromises()
  const [codeInput, nameInput, orderInput] = dialogInputs()
  await typeInto(codeInput!, code)
  await typeInto(nameInput!, name)
  await typeInto(orderInput!, order)
}

beforeEach(() => {
  api.mockReset()
  clearDocumentTypesCache()
  api.mockImplementation(async (url: string, options?: { query?: { active: boolean } }) =>
    url === '/document-types' && options?.query ? CATALOG.filter(type => type.is_active === options.query!.active) : documentType())
})
afterEach(() => { document.body.innerHTML = '' })

describe('ruta y menú de tipos de documento', () => {
  it('/document-types exige alguno de los tres tags de gestión', () => {
    const meta = useRouter().resolve('/document-types').meta.leo
    expect(meta?.tag).toEqual(ALL_DOCUMENT_TYPES_TAGS)
    expect(meta?.mode).toBe('any')
  })

  it('el menú muestra «Tipos de documento» con cualquiera de los tags y no sin ellos', async () => {
    signInWith(['leo.document-types.edit'])
    const withTag = await mountSuspended(DefaultLayout)
    expect(withTag.findAll('a').find(link => link.text().includes('Tipos de documento'))?.attributes('href')).toBe('/document-types')

    signInWith(['leo.users.view'])
    const without = await mountSuspended(DefaultLayout)
    expect(without.findAll('a').some(link => link.text().includes('Tipos de documento'))).toBe(false)
  })

  it('registra nombres legibles de los 3 permisos', () => {
    for (const tag of ALL_DOCUMENT_TYPES_TAGS) {
      expect(forbiddenMessage({ action: tag }, 'x')).toMatch(/^No tienes permiso para: .*tipos de documento/i)
    }
  })
})

describe('pantalla de tipos de documento', () => {
  it('lista activos e inactivos y el filtro oculta los inactivos', async () => {
    signInWith(ALL_DOCUMENT_TYPES_TAGS)
    const wrapper = await mountPage()
    expect(api).toHaveBeenCalledWith('/document-types', { query: { active: true } })
    expect(api).toHaveBeenCalledWith('/document-types', { query: { active: false } })
    expect(wrapper.text()).toContain('Cédula de ciudadanía')
    expect(wrapper.text()).toContain('Tipo antiguo')
    const filter = document.body.querySelector<HTMLSelectElement>('#ui-active-filter')!
    filter.value = 'active'
    filter.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    expect(wrapper.text()).not.toContain('Tipo antiguo')
  })

  it('solo muestra las acciones cuyo tag tiene la persona', async () => {
    signInWith(['leo.document-types.edit'])
    await mountPage()
    expect(byId('document-type-edit')).toHaveLength(2)
    expect(byId('document-type-create')).toHaveLength(0)
    expect(byId('document-type-toggle')).toHaveLength(0)
  })

  it('crear: envía código en mayúsculas, nombre y orden, y recarga', async () => {
    signInWith(ALL_DOCUMENT_TYPES_TAGS)
    await mountPage()
    await fillCreateForm('pa', 'Pasaporte', '30')
    submitDialog()
    await vi.waitFor(() => expect(api).toHaveBeenCalledWith('/document-types', { method: 'POST', body: { code: 'PA', name: 'Pasaporte', sort_order: 30 } }))
    await flushPromises()
    expect(api.mock.calls.filter(call => call[0] === '/document-types' && call[1]?.query)).toHaveLength(4)
  })

  it('crear con código repetido (409): mensaje en el formulario', async () => {
    signInWith(ALL_DOCUMENT_TYPES_TAGS)
    await mountPage()
    api.mockRejectedValue(new LeoApiError(409, 'duplicate', 'Ya existe un tipo de documento con el código «CC».', { code: 'CC' }))
    await fillCreateForm('CC', 'Otra', '1')
    submitDialog()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ya existe un tipo de documento'))
  })

  it('editar: el código va bloqueado y se envía solo nombre y orden', async () => {
    signInWith(ALL_DOCUMENT_TYPES_TAGS)
    await mountPage()
    byId('document-type-edit')[0]!.click()
    await flushPromises()
    const [codeInput, nameInput, orderInput] = dialogInputs()
    expect(codeInput!.disabled).toBe(true)
    expect(codeInput!.value).toBe('CC')
    await typeInto(nameInput!, 'Cédula')
    await typeInto(orderInput!, '5')
    submitDialog()
    await vi.waitFor(() => expect(api).toHaveBeenCalledWith('/document-types/CC', { method: 'PATCH', body: { name: 'Cédula', sort_order: 5 } }))
  })

  it('desactivar y activar piden confirmación y llaman a su endpoint', async () => {
    signInWith(ALL_DOCUMENT_TYPES_TAGS)
    await mountPage()
    const toggles = byId('document-type-toggle')
    expect(toggles.map(button => button.textContent?.trim())).toEqual(['Desactivar', 'Activar'])
    toggles[0]!.click()
    await flushPromises()
    expect(api).not.toHaveBeenCalledWith('/document-types/CC/deactivate', expect.anything())
    dialogButton('Desactivar').click()
    await vi.waitFor(() => expect(api).toHaveBeenCalledWith('/document-types/CC/deactivate', { method: 'POST' }))
    await flushPromises()
    byId('document-type-toggle')[1]!.click()
    await flushPromises()
    dialogButton('Activar').click()
    await vi.waitFor(() => expect(api).toHaveBeenCalledWith('/document-types/OLD/activate', { method: 'POST' }))
  })

  it('un error de carga se muestra legible', async () => {
    signInWith(ALL_DOCUMENT_TYPES_TAGS)
    api.mockRejectedValue(new TypeError('Failed to fetch'))
    await mountPage()
    expect(document.body.textContent).toContain('No se pudo conectar')
  })
})
