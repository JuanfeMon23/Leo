import type {
  AuditApplication, AuditCatalog, AuditEventRead, AuditFiltersState, AuditUser
} from '../types/audit'
import { auditCatalogFrom } from '../utils/auditLabels'
import { AUDIT_PAGE_SIZE, emptyAuditFilters } from '../utils/auditQuery'

/**
 * Estado del visor de auditoría. `draft` son los controles del formulario;
 * `applied` los filtros vigentes (se copian al pulsar «Buscar»). Los nombres
 * legibles (app, módulo, acción) salen del catálogo de las aplicaciones que
 * aparecen en la página o en el filtro; si no se puede leer, se muestran los
 * identificadores técnicos y se avisa. Ignora respuestas viejas.
 */
export function useAuditList() {
  const apiClient = useAuditApi()

  const draft = ref<AuditFiltersState>(emptyAuditFilters())
  const applied = ref<AuditFiltersState>(emptyAuditFilters())
  const items = ref<AuditEventRead[]>([])
  const total = ref(0)
  const page = ref(1)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const applications = ref<AuditApplication[]>([])
  const users = ref<AuditUser[]>([])
  const catalog = ref<AuditCatalog>({})
  const lookupError = ref<string | null>(null)
  const requested = new Set<string>()
  let ticket = 0

  function noteLookupError(err: unknown) {
    lookupError.value ??= leoErrorMessage(err)
  }

  /** Carga el catálogo (módulos y acciones con nombre) de una aplicación, una sola vez. */
  async function ensureApplication(id: string) {
    if (!id || requested.has(id)) return
    requested.add(id)
    try {
      const detail = await apiClient.getApplication(id)
      catalog.value = { ...catalog.value, ...auditCatalogFrom([detail]) }
    } catch (err) {
      noteLookupError(err)
    }
  }

  async function load() {
    const mine = ++ticket
    loading.value = true
    error.value = null
    try {
      const result = await apiClient.list(applied.value, page.value)
      if (mine !== ticket) return
      items.value = result.items
      total.value = result.total
      void Promise.all([...new Set(result.items.map(e => e.application_id))].map(ensureApplication))
    } catch (err) {
      if (mine !== ticket) return
      error.value = leoErrorMessage(err)
    } finally {
      if (mine === ticket) loading.value = false
    }
  }

  async function loadLookups() {
    const [apps, people] = await Promise.allSettled([apiClient.listApplications(), apiClient.listUsers()])
    if (apps.status === 'fulfilled') applications.value = apps.value.items
    else noteLookupError(apps.reason)
    if (people.status === 'fulfilled') users.value = people.value.items
    else noteLookupError(people.reason)
  }

  /** Aplica los controles como filtros vigentes y vuelve a la primera página. */
  function search() {
    applied.value = { ...draft.value }
    if (page.value !== 1) page.value = 1
    else void load()
  }

  function clear() {
    draft.value = emptyAuditFilters()
    search()
  }

  // Elegir otra aplicación invalida módulo y acción (dependen de ella).
  watch(() => draft.value.applicationId, (id) => {
    draft.value.module = ''
    draft.value.actionTag = ''
    void ensureApplication(id)
  })
  watch(() => draft.value.module, () => { draft.value.actionTag = '' })
  watch(page, () => void load())

  return {
    draft, applied, items, total, page, pageSize: AUDIT_PAGE_SIZE, loading, error,
    applications, users, catalog, lookupError, load, loadLookups, search, clear
  }
}

export type AuditList = ReturnType<typeof useAuditList>
