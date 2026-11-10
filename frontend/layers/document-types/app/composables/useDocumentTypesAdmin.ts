import type { DocumentTypeRead, DocumentTypeRow } from '../types/documentTypes'

/**
 * Estado de la pantalla de tipos de documento: carga todo el catálogo (activos
 * e inactivos), búsqueda y filtro activos/inactivos en cliente y activar/desactivar con
 * confirmación. Tras cualquier cambio invalida la caché compartida
 * (`useDocumentTypes`) para que los formularios de otros módulos vean lo nuevo.
 */
export function useDocumentTypesAdmin() {
  const api = useDocumentTypesApi()
  const toast = useToast()

  const items = ref<DocumentTypeRead[]>([])
  const search = ref('')
  const active = ref<boolean | undefined>(undefined)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const rows = computed<DocumentTypeRow[]>(() => {
    const term = search.value.trim().toLowerCase()
    return items.value
      .filter(type => active.value === undefined || type.is_active === active.value)
      .filter(type => !term || type.code.toLowerCase().includes(term) || type.name.toLowerCase().includes(term))
      .map(type => ({ ...type, actions: null }))
  })

  async function load() {
    loading.value = true
    error.value = null
    try {
      items.value = await api.list()
      clearDocumentTypesCache()
    } catch (err) {
      error.value = leoErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  const toggle = useConfirmAction(async (type: DocumentTypeRead) => {
    const nextActive = !type.is_active
    await api.setActive(type.code, nextActive)
    toast.success(nextActive ? `Tipo «${type.name}» activado.` : `Tipo «${type.name}» desactivado.`)
    await load()
  }, { mapError: leoErrorMessage })

  return { items, rows, search, active, loading, error, load, toggle }
}
