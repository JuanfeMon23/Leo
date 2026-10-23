import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { forbiddenMessage } from '#leo-client/lib/permissionNames'
import DefaultLayout from '../app/layouts/default.vue'
import SettingsIndexPage from '../layers/settings/app/pages/ajustes/index.vue'
import { useSettingsScreen } from '../layers/settings/app/composables/useSettingsScreen'
import { ALL_SETTINGS_TAGS, signInWith } from './helpers/session'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

function setting(over: Record<string, unknown> = {}) {
  return {
    key: 'login.max_attempts', type: 'int', value: 5, default: 5, min: 1, max: 10, unit: null,
    description: 'Intentos de inicio de sesión', version: 3, requires_security_permission: false,
    updated_at: null, updated_by: null, updated_by_username: null, ...over
  }
}
const LIST = { groups: [{ group: 'Seguridad', settings: [setting()] }] }

beforeEach(() => {
  api.mockReset()
  api.mockResolvedValue(LIST)
})
afterEach(() => { document.body.innerHTML = '' })

describe('ruta y menú de ajustes', () => {
  it('/ajustes exige leo.settings.view', () => {
    expect(useRouter().resolve('/ajustes').meta.leo?.tag).toBe('leo.settings.view')
  })

  it('el menú muestra «Ajustes» solo con leo.settings.view', async () => {
    signInWith(['leo.settings.view'])
    const withTag = await mountSuspended(DefaultLayout)
    expect(withTag.findAll('a').find(a => a.text().includes('Ajustes'))?.attributes('href')).toBe('/ajustes')

    signInWith(['leo.settings.edit', 'leo.users.view'])
    const without = await mountSuspended(DefaultLayout)
    expect(without.findAll('a').some(a => a.text().includes('Ajustes'))).toBe(false)
  })

  it('registra nombres legibles de los 3 permisos', () => {
    for (const tag of ALL_SETTINGS_TAGS) {
      expect(forbiddenMessage({ action: tag }, 'x')).toMatch(/^No tienes permiso para: .*ajustes/i)
    }
  })
})

describe('página de ajustes', () => {
  it('carga con GET /settings y lista los ajustes por grupo', async () => {
    signInWith(['leo.settings.view'])
    const wrapper = await mountSuspended(SettingsIndexPage)
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/settings')
    expect(wrapper.text()).toContain('Ajustes del sistema')
    expect(wrapper.text()).toContain('Intentos de inicio de sesión')
  })

  it('sin leo.settings.edit el valor no es editable', async () => {
    signInWith(['leo.settings.view'])
    const wrapper = await mountSuspended(SettingsIndexPage)
    await flushPromises()
    expect(wrapper.find('input').attributes('disabled')).toBeDefined()
  })

  it('con leo.settings.edit el valor es editable', async () => {
    signInWith(['leo.settings.view', 'leo.settings.edit'])
    const wrapper = await mountSuspended(SettingsIndexPage)
    await flushPromises()
    expect(wrapper.find('input').attributes('disabled')).toBeUndefined()
  })
})

describe('useSettingsScreen (permisos y capa)', () => {
  async function screen(perms: string[]) {
    signInWith(perms)
    let admin!: ReturnType<typeof useSettingsScreen>
    await mountSuspended({ setup() { admin = useSettingsScreen(); return () => null } })
    return admin
  }
  const secure = setting({ key: 'login.lockout', requires_security_permission: true })

  it('view: nada es editable', async () => {
    const admin = await screen(['leo.settings.view'])
    expect(admin.canEditSetting(setting() as never)).toBe(false)
  })

  it('edit: edita lo común pero no lo de seguridad', async () => {
    const admin = await screen(['leo.settings.view', 'leo.settings.edit'])
    expect(admin.canEditSetting(setting() as never)).toBe(true)
    expect(admin.canEditSetting(secure as never)).toBe(false)
  })

  it('edit-security: también lo de seguridad', async () => {
    const admin = await screen(ALL_SETTINGS_TAGS)
    expect(admin.canEditSetting(secure as never)).toBe(true)
  })

  it('guardar hace PUT /settings/{key} con valor, motivo y versión esperada, y avisa', async () => {
    const admin = await screen(ALL_SETTINGS_TAGS)
    await admin.load()
    const item = admin.groups[0]!.settings[0]!
    admin.setDraft(item, '7')
    expect(admin.askSave(item)).toBe(true)
    admin.reason = 'Endurecer el acceso'
    api.mockResolvedValue({ ...item, value: 7, version: 4 })
    await admin.confirmSave()
    expect(api).toHaveBeenLastCalledWith('/settings/login.max_attempts', {
      method: 'PUT', body: { value: 7, reason: 'Endurecer el acceso', expected_version: 3 }
    })
    expect(admin.groups[0]!.settings[0]!.value).toBe(7)
  })

  it('el historial pide GET /settings/{key}/history?page', async () => {
    const admin = await screen(ALL_SETTINGS_TAGS)
    await admin.load()
    api.mockResolvedValue({ items: [], page: 2, page_size: 20, total: 0 })
    await admin.openHistory(admin.groups[0]!.settings[0]!)
    await admin.setHistoryPage(2)
    expect(api).toHaveBeenLastCalledWith('/settings/login.max_attempts/history', { query: { page: 2 } })
  })

  it('el error de rango conserva code y details y sale en español', async () => {
    const admin = await screen(ALL_SETTINGS_TAGS)
    await admin.load()
    const item = admin.groups[0]!.settings[0]!
    admin.setDraft(item, '9')
    admin.askSave(item)
    admin.reason = 'Prueba de rango'
    api.mockRejectedValue(new LeoApiError(422, 'setting_out_of_range', 'raw', { min: 1, max: 10 }))
    await admin.confirmSave()
    expect(admin.saveError).toMatch(/fuera del rango/)
  })

  it('error al cargar: mensaje legible, no el crudo', async () => {
    const admin = await screen(['leo.settings.view'])
    api.mockRejectedValue(new LeoApiError(500, 'internal_error', 'Traceback (most recent call last)'))
    await admin.load()
    expect(admin.loadError).toBeTruthy()
    expect(admin.loadError).not.toContain('Traceback')
  })
})
