import type { AuditApplicationDetail, AuditCatalog, AuditEventRead, AuditResult } from '../types/audit'

type BadgeVariant = 'success' | 'warning' | 'danger'

const RESULT_LABELS: Record<AuditResult, string> = { ok: 'Permitido', denied: 'Denegado', error: 'Error' }
const RESULT_VARIANTS: Record<AuditResult, BadgeVariant> = { ok: 'success', denied: 'warning', error: 'danger' }

export const AUDIT_RESULT_OPTIONS = (Object.keys(RESULT_LABELS) as AuditResult[]).map(value => ({ value, label: RESULT_LABELS[value] }))

export const auditResultLabel = (result: AuditResult) => RESULT_LABELS[result]
export const auditResultVariant = (result: AuditResult) => RESULT_VARIANTS[result]

const ENTITY_LABELS: Record<string, string> = {
  user: 'Usuario',
  role: 'Rol',
  application: 'Aplicación',
  module: 'Módulo',
  action: 'Acción',
  session: 'Sesión',
  token: 'Token'
}

/** Índice de catálogos por id de aplicación (reactivo y serializable). */
export function auditCatalogFrom(details: AuditApplicationDetail[]): AuditCatalog {
  return Object.fromEntries(details.map(detail => [detail.id, detail]))
}

export const auditApplicationName = (catalog: AuditCatalog, applicationId: string) =>
  catalog[applicationId]?.name ?? 'Aplicación desconocida'

/** Nombre del módulo; sin catálogo, su slug; sin módulo, «—». */
export function auditModuleName(catalog: AuditCatalog, applicationId: string, slug: string | null): string {
  if (!slug) return '—'
  return catalog[applicationId]?.modules.find(m => m.slug === slug)?.name ?? slug
}

/** Nombre legible de la acción; sin catálogo, el tag técnico. */
export function auditActionName(catalog: AuditCatalog, applicationId: string, tag: string): string {
  for (const mod of catalog[applicationId]?.modules ?? []) {
    const found = mod.actions.find(a => a.tag === tag)
    if (found) return found.name
  }
  return tag
}

/** Quién hizo la acción; sin usuario (evento del sistema o acceso fallido anónimo), «Sistema». */
export const auditActorLabel = (event: Pick<AuditEventRead, 'actor_username'>) => event.actor_username || 'Sistema'

/** Sobre qué: tipo de entidad legible + identificador; `null` si el evento no es sobre una entidad. */
export function auditEntityLabel(event: Pick<AuditEventRead, 'entity_type' | 'entity_id'>): { type: string, id: string | null } | null {
  if (!event.entity_type && !event.entity_id) return null
  const type = event.entity_type ? (ENTITY_LABELS[event.entity_type] ?? event.entity_type) : 'Entidad'
  return { type, id: event.entity_id }
}
