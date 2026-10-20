import type { UserRead } from '../types/users'
import { userErrorMessage } from '../utils/userErrors'
import { USERS_PAGE_SIZE } from '../utils/userQuery'

/**
 * Estado del listado de usuarios: búsqueda (ya confirmada por `UiSearchInput`),
 * filtro activos/inactivos y paginación. Cambiar búsqueda o filtro vuelve a la
 * página 1; ignora respuestas viejas.
 */
export function useUsersList() {
  const api = useUsersApi()

  const items = ref<UserRead[]>([])
  const total = ref(0)
  const page = ref(1)
  const search = ref('')
  const active = ref<boolean | undefined>(undefined)
  const loading = ref(false)
  const error = ref<string | null>(null)
  let ticket = 0

  async function load() {
    const mine = ++ticket
    loading.value = true
    error.value = null
    try {
      const result = await api.list({ search: search.value, page: page.value, active: active.value })
      if (mine !== ticket) return
      items.value = result.items
      total.value = result.total
    } catch (err) {
      if (mine !== ticket) return
      error.value = userErrorMessage(err)
    } finally {
      if (mine === ticket) loading.value = false
    }
  }

  watch([search, active], () => {
    // Fuera de la página 1, volver a ella ya dispara la recarga (watch de `page`).
    if (page.value !== 1) page.value = 1
    else void load()
  })
  watch(page, () => void load())

  return { items, total, page, pageSize: USERS_PAGE_SIZE, search, active, loading, error, load }
}
