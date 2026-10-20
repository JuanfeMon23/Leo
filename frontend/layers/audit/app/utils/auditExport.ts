import type { AuditFiltersState } from '../types/audit'

const pad = (n: number) => String(n).padStart(2, '0')

/** `auditoria-AAAA-MM-DD.csv`, o con el rango filtrado (`auditoria-2026-10-01_a_2026-10-15.csv`). */
export function auditExportFilename(filters: Pick<AuditFiltersState, 'dateFrom' | 'dateTo'>, now: Date = new Date()): string {
  const { dateFrom, dateTo } = filters
  if (dateFrom && dateTo) return `auditoria-${dateFrom}_a_${dateTo}.csv`
  if (dateFrom) return `auditoria-desde-${dateFrom}.csv`
  if (dateTo) return `auditoria-hasta-${dateTo}.csv`
  return `auditoria-${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}.csv`
}
