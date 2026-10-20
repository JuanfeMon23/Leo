// Tipos del contrato `/api/v1/audit` (fuente: backend/app/modules/audit/schemas.py)
// y de lo que el módulo lee de `/applications` y `/users` para nombrar cosas.

export type AuditResult = 'ok' | 'denied' | 'error'

/** Valor de `changes[campo]`: `{before, after}`. */
export interface AuditChange {
  before?: unknown
  after?: unknown
}

export interface AuditEventRead {
  id: string
  occurred_at: string
  actor_user_id: string | null
  actor_username: string | null
  application_id: string
  module: string | null
  action_tag: string
  entity_type: string | null
  entity_id: string | null
  changes: Record<string, unknown> | null
  result: AuditResult
  reason: string | null
  ip: string | null
  user_agent: string | null
  session_id: string | null
  request_id: string | null
}

export interface AuditEventPage {
  items: AuditEventRead[]
  total: number
  page: number
  page_size: number
}

/** Aplicación como la necesita el módulo (selector y nombre del evento). */
export interface AuditApplication {
  id: string
  slug: string
  name: string
}

export interface AuditApplicationPage {
  items: AuditApplication[]
  total: number
  page: number
  page_size: number
}

export interface AuditCatalogAction {
  tag: string
  name: string
}

export interface AuditCatalogModule {
  slug: string
  name: string
  actions: AuditCatalogAction[]
}

/** `GET /applications/{id}` reducido a lo que se usa para dar nombres legibles. */
export interface AuditApplicationDetail extends AuditApplication {
  modules: AuditCatalogModule[]
}

/** Usuario para el filtro «Quién». */
export interface AuditUser {
  id: string
  username: string
  first_name: string
  last_name: string
}

export interface AuditUserPage {
  items: AuditUser[]
  total: number
  page: number
  page_size: number
}

/** Filtros del visor (valores de los controles; `''` = sin filtro). */
export interface AuditFiltersState {
  actorUserId: string
  actorUsername: string
  applicationId: string
  module: string
  actionTag: string
  entityType: string
  entityId: string
  result: '' | AuditResult
  /** `AAAA-MM-DD` (día local), incluido. */
  dateFrom: string
  /** `AAAA-MM-DD` (día local), incluido. */
  dateTo: string
}

/** Catálogo cargado: nombres de app, módulo y acción por id/slug/tag. */
export type AuditCatalog = Record<string, AuditApplicationDetail>
