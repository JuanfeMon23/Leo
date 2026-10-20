import type { AuditFiltersState } from '../types/audit'
import { auditExportFilename } from '../utils/auditExport'

/**
 * Exporta a CSV los filtros vigentes: la descarga viaja por la petición
 * firmada (cookie + DPoP), llega como blob y se guarda como archivo. El error
 * se deja legible en `error`.
 */
export function useAuditExport(filters: () => AuditFiltersState) {
  const api = useAuditApi()
  const toast = useToast()
  const exporting = ref(false)
  const error = ref<string | null>(null)

  async function run() {
    if (exporting.value) return
    exporting.value = true
    error.value = null
    try {
      const current = filters()
      const blob = await api.exportCsv(current)
      downloadBlob(blob, auditExportFilename(current))
      toast.success('Exportación lista: el archivo se guardó en tus descargas.')
    } catch (err) {
      error.value = `No se pudo exportar: ${leoErrorMessage(err)}`
    } finally {
      exporting.value = false
    }
  }

  return { exporting, error, run }
}
