// Tipo de documento de `GET /api/v1/document-types` (catálogo en BD, fuente: backend).
export interface DocumentTypeRead {
  code: string
  name: string
  sort_order: number
  is_active: boolean
}
