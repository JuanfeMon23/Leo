import type {
  AuditApplicationDetail, AuditApplicationPage, AuditEventPage, AuditFiltersState, AuditUserPage
} from '../types/audit'
import { buildAuditFilterParams, buildAuditQuery } from '../utils/auditQuery'

/** Máximo de `page_size` que acepta el backend (un solo viaje para los selectores). */
const SELECTOR_PAGE_SIZE = 200

/**
 * Llamadas a `/audit` (y, de solo lectura, a `/applications` y `/users` para
 * dar nombres legibles y llenar los filtros): única puerta del módulo a la
 * API. Lanzan `LeoApiError`; quien las llama muestra `leoErrorMessage(err)`.
 */
export function useAuditApi() {
  const api = useLeoApi()

  return {
    list: (filters: AuditFiltersState, page: number) =>
      api<AuditEventPage>('/audit/events', { query: buildAuditQuery(filters, page) }),
    /** CSV con los filtros activos, por la petición firmada (cookie + DPoP). */
    exportCsv: (filters: AuditFiltersState) =>
      api<Blob>('/audit/events/export', { query: buildAuditFilterParams(filters), responseType: 'blob' }),
    listApplications: () =>
      api<AuditApplicationPage>('/applications', { query: { page: 1, page_size: SELECTOR_PAGE_SIZE } }),
    getApplication: (id: string) => api<AuditApplicationDetail>(`/applications/${id}`),
    listUsers: () => api<AuditUserPage>('/users', { query: { page: 1, page_size: SELECTOR_PAGE_SIZE } })
  }
}
