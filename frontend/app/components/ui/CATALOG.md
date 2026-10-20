# Catálogo de reusables — núcleo frontend de Leo (`frontend/app/components/ui/`)

Única fuente de los componentes, composables y utilidades **propios de Leo**. Los componentes `Ui*`, tokens y utilidades de formularios genéricos los aporta **Andromeda** y no se listan aquí. Formato y regla de ubicación: patrón `reusable-catalog` de Ying. Criterios propios: skill `frontend-reusable-ui`.

| Elemento | Ubicación | Props / firma | Usado por |
|---|---|---|---|
| `isEventAction`, `EVENT_PREFIX` | `frontend/app/utils/actionEvents.ts` | `isEventAction(description: string \| null \| undefined): boolean` — las acciones de evento (descripción «Evento: …») no son permisos asignables | `applications` (insignia, sin edición), `roles` (no se ofrecen al asignar) |
| `zSlug`, `SLUG_REGEX`, `SLUG_MESSAGE` | `frontend/app/utils/slug.ts` | `zSlug(requiredMessage): ZodString` — slug/verbo kebab-case, máx. 64 (igual que `Slug` del backend) | `applications`, `roles` |
| `formatLocalDateTime` | `frontend/app/utils/dateTime.ts` | `(iso, { seconds?, fallback? }): string` — `DD/MM/AAAA HH:MM[:SS]` en hora local | `audit`, `sessions` |
| `summarizeUserAgent` | `frontend/app/utils/userAgent.ts` | `(ua): string` — «Chrome 141 en Windows»; cliente desconocido recortado; vacío → «Desconocido» | `audit`, `sessions` |
| `downloadBlob`, `safeDownloadName` | `frontend/app/utils/downloadBlob.ts` | `downloadBlob(blob, filename)` guarda un `Blob` como archivo (enlace temporal) | `audit` (export CSV) |

_Las utilidades de `app/utils/` se auto-importan en componentes; en pruebas de entorno `node` y en utils puras se importan por ruta relativa explícita. `auth` solo usa Andromeda y `leo-client`._
