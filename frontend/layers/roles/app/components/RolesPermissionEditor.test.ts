import { mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import type { RolesCatalogModule } from '../types/roles'
import { rolesBuildPermissionModel } from '../utils/rolePermissions'
import RolesPermissionEditor from './RolesPermissionEditor.vue'

enableAutoUnmount(afterEach)

const act = (id: string, verb: string, name: string, extra: Record<string, unknown> = {}) => ({
  id, verb, tag: `vladimir.samples.${verb}`, name, description: `Desc ${name}`, is_active: true, ...extra
})
const catalog: RolesCatalogModule[] = [
  {
    id: 'm1', slug: 'samples', name: 'Muestras', description: null, is_active: true,
    actions: [
      act('a1', 'view', 'Consultar muestras'),
      act('a2', 'edit', 'Editar muestras'),
      act('a3', 'old', 'Antigua', { is_active: false }),
      act('e1', 'login', 'Inicio de sesión', { description: 'Evento: inicio de sesion' })
    ]
  },
  { id: 'm2', slug: 'reports', name: 'Reportes', description: null, is_active: true, actions: [act('b1', 'view', 'Consultar reportes')] }
]
const model = rolesBuildPermissionModel(catalog, [])

const mount = (selected: string[] = [], readonly = false) =>
  mountSuspended(RolesPermissionEditor, { props: { model, selected: new Set(selected), readonly } })

describe('RolesPermissionEditor', () => {
  it('agrupa por módulo: nombre legible y descripción primero, tag pequeño y atenuado', async () => {
    const wrapper = await mount()
    const groups = wrapper.findAll('[data-testid="permission-group"]')
    expect(groups).toHaveLength(2)
    expect(groups[0]!.text()).toContain('Muestras')
    const row = groups[0]!.findAll('[data-testid="permission-row"]')[0]!
    expect(row.text()).toContain('Consultar muestras')
    expect(row.text()).toContain('Desc Consultar muestras')
    const tag = row.get('[data-testid="permission-tag"]')
    expect(tag.text()).toBe('vladimir.samples.view')
    expect(tag.classes()).toEqual(expect.arrayContaining(['text-xs', 'text-text-muted']))
  })

  it('marcar un permiso emite un conjunto nuevo con su id', async () => {
    const wrapper = await mount(['b1'])
    await wrapper.findAll('[data-testid="permission-check"] input')[0]!.setValue(true)
    const emitted = wrapper.emitted('update:selected')!
    expect([...(emitted[0]![0] as Set<string>)].sort()).toEqual(['a1', 'b1'])
  })

  it('desmarcar un permiso lo quita', async () => {
    const wrapper = await mount(['a1', 'b1'])
    await wrapper.findAll('[data-testid="permission-check"] input')[0]!.setValue(false)
    expect([...(wrapper.emitted('update:selected')![0]![0] as Set<string>)]).toEqual(['b1'])
  })

  it('«Seleccionar todo» del módulo marca solo los asignables de ese módulo', async () => {
    const wrapper = await mount(['b1'])
    await wrapper.findAll('[data-testid="group-all"] input')[0]!.setValue(true)
    expect([...(wrapper.emitted('update:selected')![0]![0] as Set<string>)].sort()).toEqual(['a1', 'a2', 'b1'])
  })

  it('muestra cuántos permisos del módulo están marcados', async () => {
    const wrapper = await mount(['a1'])
    expect(wrapper.findAll('[data-testid="group-count"]')[0]!.text()).toBe('1 de 3')
  })

  it('la acción inactiva aparece bloqueada con su motivo y no se puede marcar', async () => {
    const wrapper = await mount()
    const row = wrapper.findAll('[data-testid="permission-group"]')[0]!.findAll('[data-testid="permission-row"]')[2]!
    expect(row.text()).toContain('Acción desactivada.')
    expect(row.get('input').attributes('disabled')).toBeDefined()
  })

  it('las acciones de evento van aparte y no tienen checkbox', async () => {
    const wrapper = await mount()
    const events = wrapper.get('[data-testid="events-section"]')
    expect(events.text()).toContain('Eventos de auditoría (1)')
    expect(events.text()).toContain('Inicio de sesión')
    expect(events.find('input').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="permission-row"]').some(r => r.text().includes('Inicio de sesión'))).toBe(false)
  })

  it('solo lectura: todo deshabilitado y sin «Seleccionar todo»', async () => {
    const wrapper = await mount(['a1'], true)
    expect(wrapper.findAll('[data-testid="permission-check"] input').every(i => i.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.find('[data-testid="group-all"]').exists()).toBe(false)
  })

  it('sin permisos en la aplicación: mensaje de vacío', async () => {
    const wrapper = await mountSuspended(RolesPermissionEditor, { props: { model: { groups: [], events: [] }, selected: new Set<string>() } })
    expect(wrapper.find('[data-testid="permissions-empty"]').exists()).toBe(true)
  })
})
