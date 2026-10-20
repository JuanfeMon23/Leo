import { describe, expect, it } from 'vitest'
import type { RoleActionRead, RolesCatalogModule } from '../types/roles'
import {
  rolesBuildPermissionModel,
  rolesDiffActions,
  rolesGroupState,
  rolesSelectableIds,
  rolesSetGroup
} from './rolePermissions'

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
  { id: 'm2', slug: 'old-mod', name: 'Módulo viejo', description: null, is_active: false, actions: [act('b1', 'view', 'Ver viejo')] },
  { id: 'm3', slug: 'empty', name: 'Vacío', description: null, is_active: true, actions: [] }
]

const assigned = (id: string, name: string, moduleId = 'm1'): RoleActionRead => ({
  id, tag: `vladimir.samples.${id}`, verb: id, name, description: null, is_active: true,
  module: { id: moduleId, slug: 'samples', name: 'Muestras' }
})

describe('rolesBuildPermissionModel', () => {
  it('agrupa por módulo en orden del catálogo, con nombre legible, descripción y tag', () => {
    const { groups } = rolesBuildPermissionModel(catalog, [])
    expect(groups.map(g => g.name)).toEqual(['Muestras', 'Módulo viejo'])
    expect(groups[0]!.permissions.map(p => p.name)).toEqual(['Consultar muestras', 'Editar muestras', 'Antigua'])
    expect(groups[0]!.permissions[0]).toMatchObject({ id: 'a1', tag: 'vladimir.samples.view', description: 'Desc Consultar muestras', selectable: true })
  })

  it('las acciones de evento van aparte y no son asignables', () => {
    const { groups, events } = rolesBuildPermissionModel(catalog, [])
    expect(events.map(e => e.id)).toEqual(['e1'])
    expect(events[0]!.selectable).toBe(false)
    expect(groups.flatMap(g => g.permissions).some(p => p.id === 'e1')).toBe(false)
  })

  it('acciones inactivas y de módulos inactivos no se pueden marcar, con motivo', () => {
    const { groups } = rolesBuildPermissionModel(catalog, [])
    expect(groups[0]!.permissions.find(p => p.id === 'a3')).toMatchObject({ selectable: false, blockedReason: 'Acción desactivada.' })
    expect(groups[1]!.permissions[0]).toMatchObject({ selectable: false, blockedReason: 'Módulo desactivado.' })
  })

  it('omite módulos sin permisos', () => {
    expect(rolesBuildPermissionModel(catalog, []).groups.some(g => g.slug === 'empty')).toBe(false)
  })

  it('una acción asignada que ya no está en el catálogo igual aparece (para poder quitarla)', () => {
    const { groups } = rolesBuildPermissionModel(catalog, [assigned('zz', 'Huérfana', 'm9')])
    const orphan = groups.find(g => g.moduleId === 'm9')!
    expect(orphan.permissions[0]).toMatchObject({ id: 'zz', name: 'Huérfana', selectable: true })
  })

  it('una inactiva ya asignada se muestra, pero no se puede volver a marcar', () => {
    const inactiveAssigned: RoleActionRead = { ...assigned('a3', 'Antigua'), is_active: false }
    const { groups } = rolesBuildPermissionModel(catalog, [inactiveAssigned])
    expect(groups[0]!.permissions.find(p => p.id === 'a3')!.selectable).toBe(false)
  })
})

describe('rolesSelectableIds', () => {
  it('solo ids de permisos asignables del grupo', () => {
    const { groups } = rolesBuildPermissionModel(catalog, [])
    expect(rolesSelectableIds(groups[0]!)).toEqual(['a1', 'a2'])
    expect(rolesSelectableIds(groups[1]!)).toEqual([])
  })
})

describe('rolesGroupState / rolesSetGroup', () => {
  const [group, blocked] = rolesBuildPermissionModel(catalog, []).groups as [ReturnType<typeof rolesBuildPermissionModel>['groups'][number], ReturnType<typeof rolesBuildPermissionModel>['groups'][number]]

  it('none / some / all según lo marcado entre los asignables', () => {
    expect(rolesGroupState(group, new Set())).toBe('none')
    expect(rolesGroupState(group, new Set(['a1']))).toBe('some')
    expect(rolesGroupState(group, new Set(['a1', 'a2']))).toBe('all')
  })

  it('grupo sin asignables queda en none', () => {
    expect(rolesGroupState(blocked, new Set())).toBe('none')
  })

  it('seleccionar todo agrega solo asignables y no toca otros módulos', () => {
    expect([...rolesSetGroup(group, new Set(['zzz']), true)].sort()).toEqual(['a1', 'a2', 'zzz'])
  })

  it('quitar todo quita también lo no asignable que estuviera asignado, sin mutar la entrada', () => {
    const current = new Set(['a1', 'a3', 'zzz'])
    expect([...rolesSetGroup(group, current, false)]).toEqual(['zzz'])
    expect([...current].sort()).toEqual(['a1', 'a3', 'zzz'])
  })
})

describe('rolesDiffActions', () => {
  it('agrega lo nuevo y quita lo que ya no está', () => {
    expect(rolesDiffActions(['a', 'b'], new Set(['b', 'c']))).toEqual({ add: ['c'], remove: ['a'] })
  })

  it('sin cambios: nada', () => {
    expect(rolesDiffActions(['a'], new Set(['a']))).toEqual({ add: [], remove: [] })
  })

  it('sin repetidos', () => {
    expect(rolesDiffActions(['x', 'x'], new Set(['b', 'a']))).toEqual({ add: ['b', 'a'], remove: ['x'] })
  })
})
