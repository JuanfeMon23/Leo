import type { UiSelectOption } from '#andromeda/components/ui/UiSelect.vue'
import type { DocumentTypeRead } from '../types/documentTypes'

/** Vigencia del valor en memoria; evita pedir el catálogo en cada modal o detalle. */
const CACHE_TTL_MS = 30_000

let cached: { items: DocumentTypeRead[], at: number } | null = null
let inFlight: Promise<DocumentTypeRead[]> | null = null

/** Descarta el valor en memoria (tras gestionar el catálogo, cierre de sesión y pruebas). */
export function clearDocumentTypesCache() {
  cached = null
  inFlight = null
}

/**
 * Catálogo de tipos de documento (`GET /document-types?active=true` y `?active=false`, unidos
 * y ordenados por `sort_order`, `code`), con caché en memoria ~30 s. `types` incluye los inactivos para
 * poder nombrar un documento ya guardado; los selectores ofrecen solo los
 * activos (`selectOptions`), más el valor actual del registro aunque esté
 * inactivo. Si la carga falla, `error` trae un mensaje legible y las listas
 * quedan vacías (el backend sigue siendo la autoridad).
 */
export function useDocumentTypes() {
  const api = useLeoApi()
  const fresh = () => (cached && Date.now() - cached.at < CACHE_TTL_MS ? cached.items : null)
  const types = ref<DocumentTypeRead[]>(fresh() ?? [])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(force = false): Promise<void> {
    if (force) clearDocumentTypesCache()
    const hit = fresh()
    if (hit) {
      types.value = hit
      return
    }
    loading.value = true
    error.value = null
    try {
      inFlight ??= Promise.all([
        api<DocumentTypeRead[]>('/document-types', { query: { active: true } }),
        api<DocumentTypeRead[]>('/document-types', { query: { active: false } })
      ]).then(([active, inactive]) => mergeDocumentTypes(active, inactive))
        .then((items) => {
          cached = { items, at: Date.now() }
          return items
        })
        .finally(() => { inFlight = null })
      types.value = await inFlight
    } catch (err) {
      error.value = leoErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  /** Nombre del tipo (`Cédula de ciudadanía`); si no está en el catálogo, el propio código. */
  const nameOf = (code: string) => types.value.find(type => type.code === code)?.name ?? code

  /** Opciones de un `<UiSelect>`: activos y, si se pasa, el código actual aunque esté inactivo. */
  function selectOptions(current?: string | null): UiSelectOption[] {
    return types.value
      .filter(type => type.is_active || type.code === current)
      .map(type => ({
        value: type.code,
        label: `${type.code} · ${type.name}${type.is_active ? '' : ' (inactivo)'}`
      }))
  }

  void load()

  return { types, loading, error, load, nameOf, selectOptions }
}
