/** Contrato de `/auth/me` y `/auth/login` (MeResponse del backend). */
export interface LeoUser {
  id: string
  username: string
  email: string
  first_name: string
  last_name: string
}

export interface LeoSessionInfo {
  id: string
  expires_at: string
  last_activity_at: string
  idle_timeout_seconds: number
}

export interface LeoApplicationLink {
  slug: string
  name: string
  base_url: string
}

export interface LeoMe {
  user: LeoUser
  session: LeoSessionInfo
  /** Tags efectivos del usuario en la app actual (ordenados). */
  permissions: string[]
  /** Apps a las que tiene acceso (selector de la barra superior). */
  applications: LeoApplicationLink[]
}
