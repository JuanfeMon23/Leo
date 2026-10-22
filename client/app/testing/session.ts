import { useState } from '#imports'

/**
 * Deja una sesión de Leo autenticada con los tags dados (solo tests de
 * componentes/páginas con `LeoCan`/`useCan`/middleware). Nuxt no auto-importa
 * `testing/`: `import { signInWith } from '#leo-client/testing/session'`.
 */
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
