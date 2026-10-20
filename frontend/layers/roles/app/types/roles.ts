// Tipos del contrato `/api/v1/roles` (fuente: backend/app/modules/roles/schemas.py)
// y de lo que el módulo lee de `/api/v1/applications` (catálogo de acciones por app).

export interface RoleRead {
  id: string
  application_id: string
  slug: string
  name: string
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface RoleActionModule {
  id: string
  slug: string
  name: string
}

/** Acción asignada a un rol: nombre legible (principal), tag técnico (referencia) y su módulo. */
export interface RoleActionRead {
  id: string
  tag: string
  verb: string
  name: string
  description: string | null
  is_active: boolean
  module: RoleActionModule
}

export interface RoleDetail extends RoleRead {
  actions: RoleActionRead[]
}

export interface RolePage {
  items: RoleRead[]
  total: number
  page: number
  page_size: number
}

export interface RoleCreatePayload {
  application_id: string
  slug: string
  name: string
  description: string | null
}

export interface RoleUpdatePayload {
  name: string
  description: string | null
}

/** Aplicación como la necesita el módulo (selector y nombre del rol). */
export interface RolesApplication {
  id: string
  slug: string
  name: string
  is_active: boolean
}

export interface RolesApplicationPage {
  items: RolesApplication[]
  total: number
  page: number
  page_size: number
}

/** Catálogo de una app (`GET /applications/{id}`): módulos con sus acciones. */
export interface RolesCatalogAction {
  id: string
  verb: string
  tag: string
  name: string
  description: string | null
  is_active: boolean
}

export interface RolesCatalogModule {
  id: string
  slug: string
  name: string
  description: string | null
  is_active: boolean
  actions: RolesCatalogAction[]
}

export interface RolesCatalog {
  id: string
  slug: string
  name: string
  modules: RolesCatalogModule[]
}

// --- editor de permisos ---

/** Un permiso tal como lo muestra el editor. */
export interface RolesPermission {
  id: string
  tag: string
  name: string
  description: string | null
  /** Se puede marcar: acción activa, de módulo activo y que no es de evento. */
  selectable: boolean
  /** Por qué no se puede marcar (para mostrarlo), si aplica. */
  blockedReason: string | null
}

export interface RolesPermissionGroup {
  moduleId: string
  slug: string
  name: string
  description: string | null
  isActive: boolean
  permissions: RolesPermission[]
}

export interface RolesPermissionModel {
  /** Módulos con permisos asignables (los de evento quedan aparte). */
  groups: RolesPermissionGroup[]
  /** Acciones de evento (auditoría): solo informativas, nunca asignables. */
  events: RolesPermission[]
}
