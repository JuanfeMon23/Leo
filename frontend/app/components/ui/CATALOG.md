# Catálogo de reusables — núcleo frontend de Leo (`frontend/app/components/ui/`)

Única fuente de los componentes, composables y utilidades **propios de Leo**. Los componentes `Ui*`, tokens y utilidades de formularios genéricos los aporta **Andromeda** y no se listan aquí. Formato y regla de ubicación: patrón `reusable-catalog` de Ying. Criterios propios: skill `frontend-reusable-ui`.

| Elemento | Ubicación | Props / firma | Usado por |
|---|---|---|---|
| `isEventAction`, `EVENT_PREFIX` | `frontend/app/utils/actionEvents.ts` | `isEventAction(description: string \| null \| undefined): boolean` — las acciones de evento (descripción «Evento: …») no son permisos asignables | `applications` (insignia, sin edición), `roles` (no se ofrecen al asignar) |
| `zSlug`, `SLUG_REGEX`, `SLUG_MESSAGE` | `frontend/app/utils/slug.ts` | `zSlug(requiredMessage): ZodString` — slug/verbo kebab-case, máx. 64 (igual que `Slug` del backend) | `applications`, `roles` |
| `formatLocalDateTime` | `frontend/app/utils/dateTime.ts` | `(iso, { seconds?, fallback? }): string` — `DD/MM/AAAA HH:MM[:SS]` en hora local | `audit`, `sessions` |
| `summarizeUserAgent` | `frontend/app/utils/userAgent.ts` | `(ua): string` — «Chrome 141 en Windows»; cliente desconocido recortado; vacío → «Desconocido» | `audit`, `sessions` |
| `downloadBlob`, `safeDownloadName` | `frontend/app/utils/downloadBlob.ts` | `downloadBlob(blob, filename)` guarda un `Blob` como archivo (enlace temporal) | `audit` (export CSV) |
| `usePasswordPolicy`, `DEFAULT_PASSWORD_POLICY`, `clearPasswordPolicyCache` | `frontend/app/composables/usePasswordPolicy.ts` | `usePasswordPolicy(): { policy: Ref<PasswordPolicy>, load() }` — política de contraseña del servidor (`GET /auth/password-policy`, caché ~30 s); estricta 12/128 con las 4 clases si falla. Reemplaza la copia local de `password.ts` y `UiPasswordRequirements` (ahora `UiPasswordRequirements` y `zPassword` de Andromeda) | `users` (crear, restablecer), `profile` |
| `zLazyPassword` | `frontend/app/utils/lazyPassword.ts` | `(policy: () => PasswordPolicy, messages?): ZodLazy` — `zPassword` de Andromeda con la política leída en cada validación (el formulario nace antes de que llegue la del servidor) | `users` (alta, restablecer), `profile` (cambio) |
| `UiPasswordInput` | `#andromeda/components/ui/UiPasswordInput.vue` (capa Andromeda; su test sigue en `app/components/ui/UiPasswordInput.test.ts`) | Campo de contraseña con mostrar/ocultar; mismos props que `UiTextInput`, sin `type` | `auth` (login), `users` (crear, restablecer), `profile` |
| `zEmail`, `EMAIL_REGEX` | `frontend/app/utils/email.ts` | `zEmail` — correo obligatorio, recortado, máx. 254, forma `a@b` | `users`, `profile` |
| `formatWait` | `frontend/app/utils/formatWait.ts` | `(seconds): string` — «45 segundos», «2 minutos», «1 hora» | `auth` (429 del login), `profile` (429 de contraseña) |

_Las utilidades de `app/utils/` se auto-importan en componentes; en pruebas de entorno `node` y en utils puras se importan por ruta relativa explícita. `auth` solo usa Andromeda y `leo-client`._
