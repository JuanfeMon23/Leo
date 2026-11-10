import type { DocumentTypeCreatePayload, DocumentTypeRead, DocumentTypeUpdatePayload } from '../types/documentTypes'

/**
 * Llamadas a `/document-types`: única puerta del módulo a la API. Lanzan
 * `LeoApiError`; quien las llama muestra `leoErrorMessage(err)`.
 */
export function useDocumentTypesApi() {
  const api = useLeoApi()
  const base = '/document-types'
  const item = (code: string) => `${base}/${encodeURIComponent(code)}`

  return {
    /** Sin `active` el servidor solo devuelve activos: se piden ambos y se unen ordenados. */
    list: async () => {
      const [active, inactive] = await Promise.all([
        api<DocumentTypeRead[]>(base, { query: { active: true } }),
        api<DocumentTypeRead[]>(base, { query: { active: false } })
      ])
      return mergeDocumentTypes(active, inactive)
    },
    create: (body: DocumentTypeCreatePayload) => api<DocumentTypeRead>(base, { method: 'POST', body }),
    update: (code: string, body: DocumentTypeUpdatePayload) => api<DocumentTypeRead>(item(code), { method: 'PATCH', body }),
    setActive: (code: string, active: boolean) =>
      api<DocumentTypeRead>(`${item(code)}/${active ? 'activate' : 'deactivate'}`, { method: 'POST' })
  }
}
