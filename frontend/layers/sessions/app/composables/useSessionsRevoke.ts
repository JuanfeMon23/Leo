import type { SessionRead } from '../types/sessions'

/**
 * Revocar una sesión con confirmación (`useConfirmAction` de Andromeda con el
 * error ya legible). Revocar la propia cierra la sesión de quien la revoca: la
 * siguiente petición vuelve al login; el aviso se hace en la confirmación.
 */
export function useSessionsRevoke(onChanged: () => unknown) {
  const api = useSessionsApi()
  const toast = useToast()

  return useConfirmAction<SessionRead>(async (session) => {
    await api.revoke(session.id)
    toast.success(session.is_current ? 'Cerraste tu propia sesión.' : 'Sesión revocada.')
    await onChanged()
  }, { mapError: leoErrorMessage })
}

export type SessionsRevoke = ReturnType<typeof useSessionsRevoke>
