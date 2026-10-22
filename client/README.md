# leo-client

Capa Nuxt de Leo (sesión SSO, DPoP, permisos por tag, barra superior) que extienden las apps del ecosistema.

## Requisitos de uso

- Nuxt 4.5+, Vue 3.5+, pnpm.
- `extends: ['andromeda', 'leo-client']` (Andromeda v0.5.0 o superior, primero).
- Variables `NUXT_PUBLIC_LEO_*`: ver la cabecera de `nuxt.config.ts`.
- Para `useLeoAppApi`: `NUXT_PUBLIC_API_BASE` (API de la app) que cuelgue de `NUXT_PUBLIC_LEO_API_BASE`.
- Para `LeoAppShell`: pasar `items` ya filtrados por permisos (`useCan`).
- Para `forbiddenMessage`: registrar los nombres de permisos de la app con `registerPermissionNames({...})` una vez (plugin).
- Tests de componentes: `import { signInWith } from '#leo-client/testing/session'`.

## Ejecutar

```
pnpm install
pnpm test              # lógica pura (vitest.unit.config.ts)
pnpm test:components   # componentes con Nuxt
pnpm typecheck
```
