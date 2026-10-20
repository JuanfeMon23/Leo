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
