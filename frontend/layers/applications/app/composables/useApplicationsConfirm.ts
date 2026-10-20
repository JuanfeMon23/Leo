import { applicationErrorMessage } from '../utils/applicationErrors'

/**
 * `useConfirmAction` de Andromeda con el error ya legible (`applicationErrorMessage`):
 * el modal de confirmación nunca recibe el mensaje crudo de una excepción.
 */
export function useApplicationsConfirm<T>(action: (target: T) => Promise<unknown>) {
  return useConfirmAction<T>(async (target) => {
    try {
      await action(target)
    } catch (err) {
      throw new Error(applicationErrorMessage(err))
    }
  })
}
