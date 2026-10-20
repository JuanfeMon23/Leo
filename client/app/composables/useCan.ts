import type { LeoTagMode } from '../lib/permissions'

/**
 * ¿El usuario tiene el/los tag(s) de acción? Reactivo.
 * `const canEdit = useCan('leo.users.edit')` · `useCan(['a.b.c', 'a.b.d'], 'any')`.
 * Ocultar en la UI no es seguridad: el backend también valida.
 */
export function useCan(tags: MaybeRefOrGetter<string | readonly string[]>, mode: MaybeRefOrGetter<LeoTagMode> = 'all') {
  const session = useLeoSession()
  return computed(() => session.can(toValue(tags), toValue(mode)))
}
