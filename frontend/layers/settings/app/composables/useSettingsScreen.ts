import { useSettingsAdmin } from '#andromeda/composables/useSettingsAdmin'

/**
 * Estado de la pantalla «Ajustes del sistema»: conecta `useSettingsAdmin` de
 * Andromeda con la API de Leo, los permisos de la sesión, los avisos y los
 * mensajes de error legibles. Editar exige `leo.settings.edit`; los ajustes
 * marcados como de seguridad, además `leo.settings.edit-security`.
 */
export function useSettingsScreen() {
  const api = useSettingsApi()
  const toast = useToast()
  const canEdit = useCan('leo.settings.edit')
  const canEditSecurity = useCan('leo.settings.edit-security')

  return useSettingsAdmin({
    list: api.list,
    history: api.history,
    update: api.update,
    canEdit,
    canEditSecurity,
    mapError: leoErrorMessage,
    notify: (kind, message) => toast[kind](message)
  })
}
