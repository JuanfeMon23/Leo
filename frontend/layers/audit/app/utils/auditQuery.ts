import type { AuditFiltersState } from '../types/audit'

export const AUDIT_PAGE_SIZE = 25

export function emptyAuditFilters(): AuditFiltersState {
  return {
    actorUserId: '', actorUsername: '', applicationId: '', module: '', actionTag: '',
    entityType: '', entityId: '', result: '', dateFrom: '', dateTo: ''
  }
}

const DAY = /^(\d{4})-(\d{2})-(\d{2})$/

function localDay(day: string, offset: number): string | undefined {
  const m = DAY.exec(day)
  if (!m) return undefined
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + offset).toISOString()
}

/** Inicio (00:00 local) del día `AAAA-MM-DD`, en ISO; `undefined` si no hay fecha válida. */
export const dayStartIso = (day: string) => localDay(day, 0)

/** Inicio del día siguiente: `date_to` del backend es exclusivo y el rango del usuario incluye el último día. */
export const dayEndExclusiveIso = (day: string) => localDay(day, 1)

/** Parámetros de filtro de `GET /audit/events` y de `/events/export` (sin paginación). */
export function buildAuditFilterParams(filters: AuditFiltersState): Record<string, string> {
  const text = (value: string) => value.trim()
  const entries: Array<[string, string | undefined]> = [
    ['actor_user_id', text(filters.actorUserId)],
    ['actor_username', text(filters.actorUsername)],
    ['application_id', text(filters.applicationId)],
    ['module', text(filters.module)],
    ['action_tag', text(filters.actionTag)],
    ['entity_type', text(filters.entityType)],
    ['entity_id', text(filters.entityId)],
    ['result', filters.result],
    ['date_from', dayStartIso(filters.dateFrom)],
    ['date_to', dayEndExclusiveIso(filters.dateTo)]
  ]
  return Object.fromEntries(entries.filter(([, value]) => value)) as Record<string, string>
}

/** Query de `GET /audit/events`: filtros con valor + página. */
export function buildAuditQuery(filters: AuditFiltersState, page: number) {
  return { page, page_size: AUDIT_PAGE_SIZE, ...buildAuditFilterParams(filters) }
}

/** Cuántos filtros hay aplicados (para el botón «Limpiar filtros»). */
export function auditActiveFilterCount(filters: AuditFiltersState): number {
  return Object.values(filters).filter(value => value.trim() !== '').length
}
