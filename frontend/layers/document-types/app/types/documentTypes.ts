// Contrato de gestión de `/api/v1/document-types` (fuente: backend/app/modules/document_types).
import type { DocumentTypeRead } from '../../../../app/types/documentTypes'

export type { DocumentTypeRead }

export interface DocumentTypeCreatePayload {
  code: string
  name: string
  sort_order: number
}

export interface DocumentTypeUpdatePayload {
  name: string
  sort_order: number
}

/** Fila de la tabla: el tipo más la columna (sin dato) de acciones. */
export interface DocumentTypeRow extends DocumentTypeRead {
  actions: null
}
