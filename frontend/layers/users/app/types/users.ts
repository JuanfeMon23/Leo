// Tipos del contrato `/api/v1/users` (fuente: backend/app/modules/users/schemas.py)
// y de lo que el módulo lee de `/roles` y `/applications` (selector de roles por aplicación).

export const USERS_DOCUMENT_TYPES = ['CC', 'CE', 'TI', 'RC', 'PA', 'NIT', 'PEP', 'PPT'] as const
export type UsersDocumentType = typeof USERS_DOCUMENT_TYPES[number]

export interface UserRead {
  id: string
  username: string
  email: string
  document_type: UsersDocumentType
  document_number: string
  first_name: string
  last_name: string
  is_active: boolean
  last_login_at: string | null
  failed_login_attempts: number
  locked_until: string | null
  created_at: string
  updated_at: string
}

export interface UserRoleRead {
  id: string
  application_id: string
  slug: string
  name: string
  is_active: boolean
}

export interface UserDetail extends UserRead {
  roles: UserRoleRead[]
}

export interface UserPage {
  items: UserRead[]
  total: number
  page: number
  page_size: number
}

export interface UserCreatePayload {
  username: string
  email: string
  password: string
  document_type: UsersDocumentType
  document_number: string
  first_name: string
  last_name: string
}

export interface UserUpdatePayload {
  email: string
  document_type: UsersDocumentType
  document_number: string
  first_name: string
  last_name: string
}

/** Aplicación como la necesita el módulo (nombre de las apps y selector de roles). */
export interface UsersApplication {
  id: string
  slug: string
  name: string
  is_active: boolean
}

export interface UsersApplicationPage {
  items: UsersApplication[]
  total: number
  page: number
  page_size: number
}

/** Rol de `GET /roles` (para el selector) y de `GET /roles/{id}` (con sus acciones). */
export interface UsersRoleOption {
  id: string
  application_id: string
  slug: string
  name: string
  is_active: boolean
}

export interface UsersRolePage {
  items: UsersRoleOption[]
  total: number
  page: number
  page_size: number
}

export interface UsersRoleAction {
  id: string
  tag: string
  name: string
  is_active: boolean
}

export interface UsersRoleWithActions extends UsersRoleOption {
  actions: UsersRoleAction[]
}

// --- presentación ---

/** Roles de un usuario agrupados por aplicación. */
export interface UsersRoleGroup {
  applicationId: string
  applicationName: string
  roles: UserRoleRead[]
  /** Tiene ≥1 rol activo en la app: puede entrar a ella. */
  hasAccess: boolean
}

export type UsersStatusKind = 'active' | 'inactive' | 'locked'

export interface UsersStatus {
  kind: UsersStatusKind
  label: string
}

/** Permiso efectivo: nombre legible (principal) y tag técnico (referencia). */
export interface UsersEffectivePermission {
  id: string
  name: string
  tag: string
}

export interface UsersEffectiveGroup {
  applicationId: string
  applicationName: string
  permissions: UsersEffectivePermission[]
}
