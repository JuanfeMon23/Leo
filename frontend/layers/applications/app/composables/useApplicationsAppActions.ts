import type { ApplicationCreated, ApplicationRead, ApplicationSecretReveal } from '../types/applications'

/**
 * Acciones sobre una aplicación compartidas por el listado y el detalle:
 * activar/desactivar y rotar secreto (ambas con confirmación) y el secreto
 * que se muestra UNA vez. El secreto solo vive en `reveal` mientras la modal
 * está abierta: al cerrarla se descarta (nunca se persiste ni se registra).
 */
export function useApplicationsAppActions(onChanged: () => unknown) {
  const api = useApplicationsApi()
  const toast = useToast()

  const reveal = ref<ApplicationSecretReveal | null>(null)

  const toggle = useApplicationsConfirm(async (app: ApplicationRead) => {
    const nextActive = !app.is_active
    await api.setActive(app.id, nextActive)
    toast.success(nextActive ? `Aplicación «${app.name}» activada.` : `Aplicación «${app.name}» desactivada.`)
    await onChanged()
  })

  const rotate = useApplicationsConfirm(async (app: ApplicationRead) => {
    const rotated = await api.rotateSecret(app.id)
    reveal.value = { clientId: rotated.client_id, secret: rotated.client_secret, reason: 'rotated' }
  })

  function revealCreated(created: ApplicationCreated) {
    reveal.value = { clientId: created.application.client_id, secret: created.client_secret, reason: 'created' }
  }

  function clearReveal() {
    reveal.value = null
  }

  return { toggle, rotate, reveal, revealCreated, clearReveal }
}

export type ApplicationsAppActions = ReturnType<typeof useApplicationsAppActions>
