import type { RoleRead } from '../types/roles'

/** Activar/desactivar un rol con confirmación; lo comparten el listado y el detalle. */
export function useRolesToggle(onChanged: () => unknown) {
  const api = useRolesApi()
  const toast = useToast()

  return useRolesConfirm(async (role: RoleRead) => {
    const nextActive = !role.is_active
    await api.setActive(role.id, nextActive)
    toast.success(nextActive ? `Rol «${role.name}» activado.` : `Rol «${role.name}» desactivado.`)
    await onChanged()
  })
}

export type RolesToggle = ReturnType<typeof useRolesToggle>
