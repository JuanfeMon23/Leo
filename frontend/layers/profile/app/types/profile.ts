// Contrato de `/api/v1/auth/me/*` (fuente: backend/app/modules/auth/{router,schemas}.py).
// La respuesta de `PATCH /auth/me/profile` es el `MeResponse` de la sesión (`LeoMe` de leo-client).

/** Cuerpo de `PATCH /auth/me/profile`: solo lo que cambió. */
export interface ProfileUpdatePayload {
  first_name?: string
  last_name?: string
  email?: string
}

/** Cuerpo de `POST /auth/me/password`. Solo viaja en la petición; no se guarda. */
export interface ProfilePasswordPayload {
  current_password: string
  new_password: string
}
