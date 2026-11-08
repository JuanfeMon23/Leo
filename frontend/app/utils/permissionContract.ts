import contractJson from '../generated/permissions.json'

/**
 * Contrato de permisos generado por el backend (`uv run python -m app.core.permissions_export`).
 * Es la única fuente de nombres legibles y listas de tags del frontend: no se copian a mano.
 */
export interface ContractAction {
  tag: string
  verb: string
  name: string
  description: string
  assignable: boolean
}

export interface ContractModule {
  slug: string
  name: string
  description: string
  actions: ContractAction[]
}

export interface PermissionContract {
  app: string
  modules: ContractModule[]
}

export const PERMISSION_CONTRACT: PermissionContract = contractJson

export const CONTRACT_ACTIONS: ContractAction[] = PERMISSION_CONTRACT.modules.flatMap(module => module.actions)

/** tag -> nombre legible, solo de las acciones asignables (los eventos no son permisos). */
export const PERMISSION_NAMES: Record<string, string> = Object.fromEntries(
  CONTRACT_ACTIONS.filter(contractAction => contractAction.assignable).map(contractAction => [contractAction.tag, contractAction.name])
)

/** Tags asignables de un módulo (`users`, `auth`…). */
export function assignableTagsOf(moduleSlug: string): string[] {
  const mod = PERMISSION_CONTRACT.modules.find(module => module.slug === moduleSlug)
  return mod ? mod.actions.filter(action => action.assignable).map(action => action.tag) : []
}
