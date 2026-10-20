import { useState } from '#imports'

/** Deja una sesión autenticada con los tags dados (para pruebas de componentes con `LeoCan`/`useCan`). */
export function signInWith(permissions: string[]) {
  useState('leo-session').value = {
    status: 'authenticated',
    me: {
      user: { id: 'u1', username: 'ana', email: 'a@x.co', first_name: 'Ana', last_name: 'Pérez' },
      session: { id: 's', expires_at: '', last_activity_at: '', idle_timeout_seconds: 0 },
      permissions,
      applications: []
    }
  }
}

export const ALL_APPLICATIONS_TAGS = [
  'leo.applications.view',
  'leo.applications.create',
  'leo.applications.edit',
  'leo.applications.deactivate',
  'leo.applications.rotate-secret'
]

export const ALL_ROLES_TAGS = [
  'leo.roles.view',
  'leo.roles.create',
  'leo.roles.edit',
  'leo.roles.deactivate'
]

export const ALL_USERS_TAGS = [
  'leo.users.view',
  'leo.users.create',
  'leo.users.edit',
  'leo.users.deactivate',
  'leo.users.unlock',
  'leo.users.reset-password',
  'leo.users.assign-roles'
]
