import type { DocumentTypeRead } from '../types/documentTypes'

/** Une activos e inactivos (el backend los entrega por separado) ordenados por `sort_order` y `code`. */
export function mergeDocumentTypes(active: DocumentTypeRead[], inactive: DocumentTypeRead[]): DocumentTypeRead[] {
  return [...active, ...inactive].sort((first, second) =>
    first.sort_order - second.sort_order || first.code.localeCompare(second.code))
}
