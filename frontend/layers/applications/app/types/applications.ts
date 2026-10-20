// Tipos del contrato `/api/v1/applications` (fuente: backend/app/modules/applications/schemas.py).

export interface ApplicationRead {
  id: string
  slug: string
  name: string
  description: string | null
  base_url: string
  redirect_uris: string[]
  client_id: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ApplicationCreated {
  application: ApplicationRead
  /** En claro, solo en esta respuesta: no se guarda ni se registra. */
  client_secret: string
}

export interface ApplicationSecretRotated {
  client_id: string
  client_secret: string
}

export interface ApplicationActionRead {
  id: string
  module_id: string
  verb: string
  tag: string
  /** Nombre legible del permiso (lo principal en la UI); el tag es la referencia técnica. */
  name: string
  description: string | null
  is_active: boolean
}

export interface ApplicationModuleRead {
  id: string
  application_id: string
  slug: string
  name: string
  description: string | null
  is_active: boolean
}

export interface ApplicationModuleWithActions extends ApplicationModuleRead {
  actions: ApplicationActionRead[]
}

export interface ApplicationDetail extends ApplicationRead {
  modules: ApplicationModuleWithActions[]
}

export interface ApplicationPage {
  items: ApplicationRead[]
  total: number
  page: number
  page_size: number
}

export interface ApplicationPayload {
  slug?: string
  name: string
  description: string | null
  base_url: string
  redirect_uris: string[]
}

/** Secreto a mostrar UNA vez (modal de un solo uso). */
export interface ApplicationSecretReveal {
  clientId: string
  secret: string
  /** `created` o `rotated`: cambia el título/texto de la modal. */
  reason: 'created' | 'rotated'
}

// --- acceso entre aplicaciones (credenciales de servicio) ---
// Fuente: backend/app/modules/roles/schemas.py (concesiones de `/applications/{id}/service-access`).

export interface ApplicationsGrantPermission {
  id: string
  tag: string
  verb: string
  /** Nombre legible (lo principal); el tag es la referencia técnica. */
  name: string
  description: string | null
  is_active: boolean
  module: { id: string, slug: string, name: string }
}

export interface ApplicationsGrantRole {
  id: string
  slug: string
  name: string
  is_active: boolean
}

export interface ApplicationsGrantTarget {
  id: string
  slug: string
  name: string
}

/** Una concesión: la app llamadora puede consultar `application` con los permisos de `role`. */
export interface ApplicationsServiceGrant {
  id: string
  role: ApplicationsGrantRole
  application: ApplicationsGrantTarget
  permissions: ApplicationsGrantPermission[]
  created_at: string
}

/** Concesiones agrupadas por aplicación destino. */
export interface ApplicationsServiceGrantGroup {
  application: ApplicationsGrantTarget
  grants: ApplicationsServiceGrant[]
}

/** Rol ofrecido en el modal de conceder, con sus permisos (null = no se pudieron cargar). */
export interface ApplicationsGrantableRole {
  id: string
  slug: string
  name: string
  description: string | null
  permissions: ApplicationsGrantPermission[] | null
}

/** Página de roles (`GET /roles`) tal como la lee este módulo (solo lo que necesita). */
export interface ApplicationsRolePage {
  items: Array<{ id: string, slug: string, name: string, description: string | null, is_active: boolean }>
  total: number
}
