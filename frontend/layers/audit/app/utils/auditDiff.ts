export const EMPTY_VALUE = '(vacío)'
export const MASKED_VALUE = '••••••••'

export type AuditDiffKind = 'changed' | 'added' | 'removed' | 'unchanged'

export interface AuditDiffRow {
  field: string
  /** Nombre legible del campo. */
  label: string
  kind: AuditDiffKind
  before: string
  after: string
  /** El campo es sensible: sus valores no se muestran. */
  sensitive: boolean
}

const SENSITIVE = /pass(word|wd)?|secret|token|hash|salt|credential|dpop|jkt|key/i

const FIELD_LABELS: Record<string, string> = {
  name: 'Nombre',
  slug: 'Identificador',
  description: 'Descripción',
  username: 'Usuario',
  email: 'Correo',
  first_name: 'Nombres',
  last_name: 'Apellidos',
  document_type: 'Tipo de documento',
  document_number: 'Número de documento',
  is_active: 'Activo',
  base_url: 'URL base',
  redirect_uris: 'URIs de redirección',
  revoked_reason: 'Motivo de revocación',
  revoked_at: 'Revocada el',
  locked_until: 'Bloqueado hasta',
  failed_login_attempts: 'Intentos fallidos',
  roles: 'Roles',
  actions: 'Acciones',
  verb: 'Verbo'
}

export const auditFieldLabel = (field: string) => FIELD_LABELS[field] ?? field

/** Valor legible: vacío → «(vacío)», booleanos → Sí/No, listas separadas por coma. */
export function auditFormatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return EMPTY_VALUE
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (Array.isArray(value)) return value.length ? value.map(v => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v))).join(', ') : EMPTY_VALUE
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const isBeforeAfter = (value: unknown): value is { before?: unknown, after?: unknown } =>
  typeof value === 'object' && value !== null && !Array.isArray(value) && ('before' in value || 'after' in value)

const isEmpty = (value: unknown) => value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)

/**
 * Filas del diff `{campo: {before, after}}` de un evento: antes → después,
 * clasificadas (cambiado, agregado, quitado, sin cambio) y ordenadas por
 * campo. Los campos sensibles se enmascaran aunque el backend ya los descarte.
 */
export function auditDiffRows(changes: Record<string, unknown> | null | undefined): AuditDiffRow[] {
  if (!changes) return []
  return Object.keys(changes).sort().map((field) => {
    const raw = changes[field]
    const { before, after } = isBeforeAfter(raw) ? raw : { before: undefined, after: raw }
    const sensitive = SENSITIVE.test(field)
    const kind: AuditDiffKind = JSON.stringify(before ?? null) === JSON.stringify(after ?? null)
      ? 'unchanged'
      : isEmpty(before) ? 'added' : isEmpty(after) ? 'removed' : 'changed'
    return {
      field,
      label: auditFieldLabel(field),
      // Un campo sensible siempre se reporta como cambiado, sin revelar su valor.
      kind: sensitive ? 'changed' : kind,
      before: sensitive ? MASKED_VALUE : auditFormatValue(before),
      after: sensitive ? MASKED_VALUE : auditFormatValue(after),
      sensitive
    }
  })
}
