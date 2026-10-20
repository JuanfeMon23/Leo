import { userErrorMessage } from '../utils/userErrors'

/**
 * `useConfirmAction` de Andromeda con el error ya legible (`userErrorMessage`):
 * el modal de confirmación nunca recibe el mensaje crudo de una excepción.
 */
export function useUsersConfirm<T>(action: (target: T) => Promise<unknown>) {
  return useConfirmAction<T>(async (target) => {
    try {
      await action(target)
    } catch (err) {
      throw new Error(userErrorMessage(err))
    }
  })
}
