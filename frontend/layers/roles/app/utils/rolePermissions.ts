import type {
  RoleActionRead,
  RolesCatalogModule,
  RolesPermission,
  RolesPermissionGroup,
  RolesPermissionModel
} from '../types/roles'
import { isEventAction } from '../../../../app/utils/actionEvents'

const EVENT_REASON = 'Acción de evento: solo se audita, no se asigna.'
const ACTION_INACTIVE_REASON = 'Acción desactivada.'
const MODULE_INACTIVE_REASON = 'Módulo desactivado.'

/**
 * Arma lo que muestra el editor de permisos: las acciones del catálogo de la
 * app agrupadas por módulo (en el orden del catálogo), con nombre legible,
 * descripción y tag. Las acciones de evento van aparte (`events`) y nunca son
 * asignables; las inactivas (o de módulos inactivos) se muestran pero no se
 * pueden marcar. Lo ya asignado que el catálogo no trae (p. ej. cambió desde
 * que se cargó) se agrega a su módulo para que se pueda quitar.
 */
export function rolesBuildPermissionModel(
  modules: readonly RolesCatalogModule[],
  assigned: readonly RoleActionRead[]
): RolesPermissionModel {
  const groups: RolesPermissionGroup[] = []
  const events: RolesPermission[] = []
  const known = new Set<string>()

  for (const module of modules) {
    const permissions: RolesPermission[] = []
    for (const action of module.actions) {
      known.add(action.id)
      const base = { id: action.id, tag: action.tag, name: action.name, description: action.description }
      if (isEventAction(action.description)) {
        events.push({ ...base, selectable: false, blockedReason: EVENT_REASON })
      } else if (!module.is_active) {
        permissions.push({ ...base, selectable: false, blockedReason: MODULE_INACTIVE_REASON })
      } else if (!action.is_active) {
        permissions.push({ ...base, selectable: false, blockedReason: ACTION_INACTIVE_REASON })
      } else {
        permissions.push({ ...base, selectable: true, blockedReason: null })
      }
    }
    groups.push({ moduleId: module.id, slug: module.slug, name: module.name, description: module.description, isActive: module.is_active, permissions })
  }

  for (const action of assigned) {
    if (known.has(action.id) || isEventAction(action.description)) continue
    let group = groups.find(g => g.moduleId === action.module.id)
    if (!group) {
      group = { moduleId: action.module.id, slug: action.module.slug, name: action.module.name, description: null, isActive: true, permissions: [] }
      groups.push(group)
    }
    group.permissions.push({
      id: action.id,
      tag: action.tag,
      name: action.name,
      description: action.description,
      selectable: action.is_active,
      blockedReason: action.is_active ? null : ACTION_INACTIVE_REASON
    })
  }

  return { groups: groups.filter(g => g.permissions.length > 0), events }
}

/** Ids que se pueden marcar en un módulo. */
export function rolesSelectableIds(group: RolesPermissionGroup): string[] {
  return group.permissions.filter(p => p.selectable).map(p => p.id)
}

/** Estado del «seleccionar todo» del módulo, sobre sus permisos asignables. */
export function rolesGroupState(group: RolesPermissionGroup, selected: ReadonlySet<string>): 'none' | 'some' | 'all' {
  const ids = rolesSelectableIds(group)
  const count = ids.filter(id => selected.has(id)).length
  if (count === 0) return 'none'
  return count === ids.length ? 'all' : 'some'
}

/**
 * «Seleccionar todo / ninguno» de un módulo: marcar agrega solo los asignables;
 * desmarcar quita todo lo del módulo (incluso lo no asignable ya asignado).
 * Devuelve un conjunto nuevo.
 */
export function rolesSetGroup(group: RolesPermissionGroup, selected: ReadonlySet<string>, on: boolean): Set<string> {
  const next = new Set(selected)
  if (on) {
    for (const id of rolesSelectableIds(group)) next.add(id)
  } else {
    for (const permission of group.permissions) next.delete(permission.id)
  }
  return next
}

/** Cambios para pasar de lo asignado (`original`) a lo elegido (`desired`). */
export function rolesDiffActions(original: readonly string[], desired: ReadonlySet<string>): { add: string[], remove: string[] } {
  const before = new Set(original)
  return {
    add: [...desired].filter(id => !before.has(id)),
    remove: [...before].filter(id => !desired.has(id))
  }
}
