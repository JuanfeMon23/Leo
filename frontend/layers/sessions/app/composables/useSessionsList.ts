import type { SessionRead, SessionsUser } from '../types/sessions'
import { SESSIONS_PAGE_SIZE } from '../utils/sessionQuery'

/**
 * Estado del listado de sesiones: usuario (vacío = las propias), «solo
 * activas» y paginación. Cambiar un filtro vuelve a la página 1; ignora
 * respuestas viejas. Los usuarios (para el selector y para nombrar al dueño)
 * se cargan aparte: si no se pueden leer, el listado funciona igual y se avisa.
 */
export function useSessionsList() {
  const apiClient = useSessionsApi()

  const items = ref<SessionRead[]>([])
  const total = ref(0)
  const page = ref(1)
  const userId = ref('')
  const activeOnly = ref(true)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const users = ref<SessionsUser[]>([])
  const usersError = ref<string | null>(null)
  let ticket = 0

  async function load() {
    const mine = ++ticket
    loading.value = true
    error.value = null
    try {
      const result = await apiClient.list({ userId: userId.value, activeOnly: activeOnly.value, page: page.value })
      if (mine !== ticket) return
      items.value = result.items
      total.value = result.total
    } catch (err) {
      if (mine !== ticket) return
      error.value = leoErrorMessage(err)
    } finally {
      if (mine === ticket) loading.value = false
    }
  }

  async function loadUsers() {
    usersError.value = null
    try {
      users.value = (await apiClient.listUsers()).items
    } catch (err) {
      usersError.value = leoErrorMessage(err)
    }
  }

  watch([userId, activeOnly], () => {
    // Fuera de la página 1, volver a ella ya dispara la recarga (watch de `page`).
    if (page.value !== 1) page.value = 1
    else void load()
  })
  watch(page, () => void load())

  return { items, total, page, pageSize: SESSIONS_PAGE_SIZE, userId, activeOnly, loading, error, users, usersError, load, loadUsers }
}
