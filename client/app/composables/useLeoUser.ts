/** Usuario autenticado (o `null`). */
export function useLeoUser() {
  return useLeoSession().user
}
