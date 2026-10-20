import { describe, expect, it } from 'vitest'
import type { UserRoleRead, UsersApplication, UsersRoleOption, UsersRoleWithActions } from '../types/users'
import { usersAccessApps, usersEffectivePermissions, usersGroupRolesByApp, usersRoleOptions } from './userRoles'

const apps: UsersApplication[] = [
  { id: 'a-leo', slug: 'leo', name: 'Leo', is_active: true },
  { id: 'a-tau', slug: 'taurus', name: 'Taurus', is_active: true },
  { id: 'a-old', slug: 'old', name: 'Vieja', is_active: false }
]
const role = (id: string, application_id: string, name: string, is_active = true): UserRoleRead =>
  ({ id, application_id, slug: id, name, is_active })

describe('usersGroupRolesByApp', () => {
  it('agrupa por aplicación (orden alfabético) con roles ordenados por nombre', () => {
    const groups = usersGroupRolesByApp(
      [role('r1', 'a-tau', 'Cajero'), role('r2', 'a-leo', 'Soporte'), role('r3', 'a-leo', 'Administrador')],
      apps
    )
    expect(groups.map(g => g.applicationName)).toEqual(['Leo', 'Taurus'])
    expect(groups[0]!.roles.map(r => r.name)).toEqual(['Administrador', 'Soporte'])
  })

  it('hasAccess solo con ≥1 rol activo en la app', () => {
    const groups = usersGroupRolesByApp([role('r1', 'a-leo', 'A', false), role('r2', 'a-tau', 'B', true)], apps)
    expect(Object.fromEntries(groups.map(g => [g.applicationName, g.hasAccess]))).toEqual({ Leo: false, Taurus: true })
  })

  it('una app desconocida se nombra «Aplicación desconocida»', () => {
    const [g] = usersGroupRolesByApp([role('r1', 'zzz', 'X')], apps)
    expect(g!.applicationName).toBe('Aplicación desconocida')
  })

  it('sin roles → sin grupos', () => {
    expect(usersGroupRolesByApp([], apps)).toEqual([])
  })
})

describe('usersAccessApps', () => {
  it('nombres de las apps con rol activo', () => {
    const groups = usersGroupRolesByApp([role('r1', 'a-leo', 'A', true), role('r2', 'a-tau', 'B', false)], apps)
    expect(usersAccessApps(groups)).toEqual(['Leo'])
  })
})

describe('usersRoleOptions', () => {
  const all: UsersRoleOption[] = [
    { id: 'r1', application_id: 'a-leo', slug: 'adm', name: 'Administrador', is_active: true },
    { id: 'r2', application_id: 'a-tau', slug: 'caj', name: 'Cajero', is_active: true },
    { id: 'r3', application_id: 'a-tau', slug: 'aud', name: 'Auditor', is_active: false },
    { id: 'r4', application_id: 'a-old', slug: 'x', name: 'Zeta', is_active: true }
  ]
  it('«Aplicación → Rol», solo roles activos de apps activas y sin los ya asignados', () => {
    const opts = usersRoleOptions(all, apps, new Set(['r1']))
    expect(opts).toEqual([{ value: 'r2', label: 'Taurus → Cajero' }])
  })
  it('ordenadas por aplicación y luego por rol', () => {
    const more = [...all, { id: 'r5', application_id: 'a-leo', slug: 's', name: 'Soporte', is_active: true }]
    expect(usersRoleOptions(more, apps, new Set()).map(o => o.label)).toEqual(['Leo → Administrador', 'Leo → Soporte', 'Taurus → Cajero'])
  })
})

describe('usersEffectivePermissions', () => {
  const rwa = (id: string, application_id: string, name: string, actions: Array<[string, string, string, boolean?]>, is_active = true): UsersRoleWithActions => ({
    id, application_id, slug: id, name, is_active,
    actions: actions.map(([aid, tag, aname, act = true]) => ({ id: aid, tag, name: aname, is_active: act }))
  })
  it('une las acciones activas de los roles activos, sin repetir, por aplicación y con el nombre legible', () => {
    const groups = usersEffectivePermissions([
      rwa('r1', 'a-leo', 'A', [['x1', 'leo.users.view', 'Consultar usuarios'], ['x2', 'leo.users.edit', 'Editar usuarios', false]]),
      rwa('r2', 'a-leo', 'B', [['x1', 'leo.users.view', 'Consultar usuarios'], ['x3', 'leo.roles.view', 'Consultar roles']]),
      rwa('r3', 'a-tau', 'C', [['x4', 'taurus.caja.view', 'Ver caja']], false)
    ], apps)
    expect(groups).toEqual([{
      applicationId: 'a-leo',
      applicationName: 'Leo',
      permissions: [
        { id: 'x3', name: 'Consultar roles', tag: 'leo.roles.view' },
        { id: 'x1', name: 'Consultar usuarios', tag: 'leo.users.view' }
      ]
    }])
  })
})
