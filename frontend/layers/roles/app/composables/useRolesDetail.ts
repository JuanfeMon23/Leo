import type { RoleDetail, RolesCatalog } from '../types/roles'
import { roleErrorMessage } from '../utils/roleErrors'
import { rolesBuildPermissionModel, rolesDiffActions } from '../utils/rolePermissions'

/**
 * Estado del detalle de un rol y de su borrador de permisos. El rol sale de
 * `GET /roles/{id}` y las acciones disponibles del catálogo de su app
 * (`GET /applications/{id}`). Los cambios del editor se acumulan en
 * `selected` y `save()` los aplica: un `POST` con lo agregado y un `DELETE`
 * por cada acción quitada. Si algo falla a medias se recarga el rol (lo que
 * sí quedó guardado) y el borrador se conserva para reintentar.
 */
export function useRolesDetail(roleId: () => string) {
  const api = useRolesApi()
  const toast = useToast()

  const role = ref<RoleDetail | null>(null)
  const catalog = ref<RolesCatalog | null>(null)
  const selected = ref<Set<string>>(new Set())
  const loading = ref(false)
  const error = ref<string | null>(null)
  const catalogError = ref<string | null>(null)
  const saving = ref(false)
  const saveError = ref<string | null>(null)

  const model = computed(() => rolesBuildPermissionModel(catalog.value?.modules ?? [], role.value?.actions ?? []))
  const diff = computed(() => rolesDiffActions((role.value?.actions ?? []).map(a => a.id), selected.value))
  const dirty = computed(() => diff.value.add.length + diff.value.remove.length > 0)

  function resetDraft() {
    selected.value = new Set((role.value?.actions ?? []).map(a => a.id))
  }

  async function loadCatalog(applicationId: string) {
    catalogError.value = null
    try {
      catalog.value = await api.getCatalog(applicationId)
    } catch (err) {
      catalog.value = null
      catalogError.value = roleErrorMessage(err)
    }
  }

  async function load() {
    loading.value = true
    error.value = null
    try {
      role.value = await api.get(roleId())
      resetDraft()
      await loadCatalog(role.value.application_id)
    } catch (err) {
      role.value = null
      error.value = roleErrorMessage(err)
    } finally {
      loading.value = false
    }
  }

  /** Recarga solo los datos del rol (tras editarlo/activarlo), sin perder el borrador de permisos. */
  async function refreshRole() {
    const fresh = await api.get(roleId())
    role.value = fresh
  }

  async function save() {
    if (!role.value || !dirty.value) return
    const { add, remove } = diff.value
    saving.value = true
    saveError.value = null
    try {
      let result = role.value
      if (add.length) result = await api.addActions(result.id, add)
      for (const actionId of remove) result = await api.removeAction(result.id, actionId)
      role.value = result
      resetDraft()
      toast.success(`Permisos del rol «${result.name}» actualizados.`)
    } catch (err) {
      saveError.value = roleErrorMessage(err)
      try {
        await refreshRole()
      } catch {
        // Si tampoco se puede recargar, queda el mensaje del error original.
      }
    } finally {
      saving.value = false
    }
  }

  function discard() {
    saveError.value = null
    resetDraft()
  }

  return { role, catalog, selected, model, diff, dirty, loading, error, catalogError, saving, saveError, load, refreshRole, save, discard }
}
