import { roleErrorMessage } from '../utils/roleErrors'

/**
 * `useConfirmAction` de Andromeda con el error ya legible (`roleErrorMessage`):
 * el modal de confirmación nunca recibe el mensaje crudo de una excepción.
 */
export function useRolesConfirm<T>(action: (target: T) => Promise<unknown>) {
  return useConfirmAction<T>(async (target) => {
    try {
      await action(target)
    } catch (err) {
      throw new Error(roleErrorMessage(err))
    }
  })
}
