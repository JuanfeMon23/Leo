import type { RoleRead, RolesApplication } from '../types/roles'
import { roleErrorMessage } from '../utils/roleErrors'
import { ROLES_PAGE_SIZE } from '../utils/roleQuery'

/**
 * Estado del listado de roles: búsqueda (ya confirmada por `UiSearchInput`),
 * filtros de aplicación y activos/inactivos, y paginación. Cambiar búsqueda o
 * filtro vuelve a la página 1; ignora respuestas viejas. Las aplicaciones
 * (para el selector y para nombrar la app de cada rol) se cargan aparte: si
 * no se pueden leer, el listado funciona igual y se avisa.
 */
export function useRolesList() {
  const apiClient = useRolesApi()

  const items = ref<RoleRead[]>([])
  const total = ref(0)
  const page = ref(1)
  const search = ref('')
  const active = ref<boolean | undefined>(undefined)
  const applicationId = ref('')
  const loading = ref(false)
  const error = ref<string | null>(null)
  const applications = ref<RolesApplication[]>([])
  const applicationsError = ref<string | null>(null)
  let ticket = 0

  async function load() {
    const mine = ++ticket
    loading.value = true
    error.value = null
    try {
      const result = await apiClient.list({
        search: search.value,
        page: page.value,
        active: active.value,
        applicationId: applicationId.value
      })
      if (mine !== ticket) return
      items.value = result.items
      total.value = result.total
    } catch (err) {
      if (mine !== ticket) return
      error.value = roleErrorMessage(err)
    } finally {
      if (mine === ticket) loading.value = false
    }
  }

  async function loadApplications() {
    applicationsError.value = null
    try {
      applications.value = (await apiClient.listApplications()).items
    } catch (err) {
      applicationsError.value = roleErrorMessage(err)
    }
  }

  const applicationName = (id: string) => applications.value.find(a => a.id === id)?.name ?? '—'

  watch([search, active, applicationId], () => {
    // Fuera de la página 1, volver a ella ya dispara la recarga (watch de `page`).
    if (page.value !== 1) page.value = 1
    else void load()
  })
  watch(page, () => void load())

  return {
    items, total, page, pageSize: ROLES_PAGE_SIZE, search, active, applicationId, loading, error,
    applications, applicationsError, applicationName, load, loadApplications
  }
}
