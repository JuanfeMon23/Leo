import { fileURLToPath } from 'node:url'

/**
 * leo-client: capa Nuxt de Leo que extiende cada app del ecosistema (y el
 * propio frontend de Leo). Aporta sesión SSO con DPoP, permisos por tag
 * (`<LeoCan>`, `useCan`), middleware de ruta por tag, control de inactividad
 * y la barra superior `LeoTopBar`.
 *
 * Requisitos de la app que la extiende: extender también Andromeda (antes que
 * esta capa: `extends: ['andromeda', 'leo-client']`), porque los componentes
 * de la barra usan `Ui*` y los tokens de Andromeda.
 *
 * ── Contrato de la barra superior (<LeoTopBar>), idéntica en todas las apps ──
 * `LeoTopBar` renderiza SU PROPIO `<header>` completo (alto h-14, fondo, borde,
 * sticky top-0, z-20, padding). La app lo monta como hijo directo de la
 * columna de contenido (la que deja sitio a su menú lateral), SIN envolverlo
 * en contenedores con estilos propios ni pasarle `class`, y SIN repetir
 * dentro ni el nombre de la app ni el usuario. Solo aporta:
 *   - `#start`: hamburguesa del menú lateral (`UiButton` ghost, `icon-only`,
 *     `lg:hidden`, `aria-label="Abrir menú"`) o logo, según su layout;
 *   - `#end` (opcional): acciones propias de la app (botones pequeños de
 *     `h-10`), a la izquierda del selector de aplicaciones.
 * `appName` (prop) solo si el nombre de Leo no sirve; por defecto sale de
 * `NUXT_PUBLIC_LEO_APP_SLUG`/`APP_NAME`. Sin modo oscuro: Andromeda no define
 * tokens oscuros (la barra solo usa tokens, así que lo heredará).
 *
 * ── Configuración para APPS del ecosistema (transporte `bff`) ──────────────
 * La app habla solo con SU backend (FastAPI con `leo_sdk` y `leo_router`).
 * Variables (`.env` de la app Nuxt), mínimas:
 *
 *   NUXT_PUBLIC_LEO_TRANSPORT=bff
 *   NUXT_PUBLIC_LEO_API_BASE=http://localhost:8200      # backend de la app (sin /api/v1 salvo que lo monte así)
 *   NUXT_PUBLIC_LEO_PUBLIC_URL=http://localhost:8200    # = PUBLIC_URL del backend (fija el `htu` de DPoP)
 *   NUXT_PUBLIC_LEO_APP_SLUG=vladimir                   # = client_id de la app en Leo
 *   NUXT_PUBLIC_LEO_APP_NAME=Vladimir
 *
 * Opcionales: NUXT_PUBLIC_LEO_AUTH_PATH (prefijo de `leo_router`, `/auth`),
 * NUXT_PUBLIC_LEO_URL (URL pública del frontend de Leo, p. ej. http://localhost:3100:
 * destino de "Mi perfil" en el menú de usuario, `<url>/profile?return=<URL de la app>`;
 * sin ella el enlace se oculta), NUXT_PUBLIC_LEO_CALLBACK_PATH (ruta del FRONTEND que recibe `?code&state`,
 * `/auth/callback`) y NUXT_PUBLIC_LEO_IDLE_TIMEOUT_SECONDS (1800: `leo_sdk` no
 * entrega el tiempo de inactividad en `/auth/me`).
 *
 * La ruta del frontend `callbackPath` (URL pública del frontend + esa ruta)
 * debe coincidir con la `redirect_uri` registrada para la app en Leo y con
 * `APP_REDIRECT_URI` del backend (por defecto el SDK usa `PUBLIC_URL/auth/callback`:
 * si backend y frontend NO comparten origen, o el proxy del origen común manda
 * `/auth/*` al backend, define `APP_REDIRECT_URI` y `callbackPath` con una ruta
 * propia del frontend, p. ej. `/leo/callback`). En `bff` no se usa `loginPath`.
 */
export default defineNuxtConfig({
  // Registra la página de retorno de login en `callbackPath` (configurable).
  modules: [fileURLToPath(new URL('./modules/callbackRoute.ts', import.meta.url))],
  // La sesión depende de una llave DPoP que solo existe en el navegador
  // (IndexedDB, no exportable): el servidor de Nuxt no puede firmar pruebas
  // ni conocer los permisos. Renderizar en el servidor produciría páginas sin
  // permisos y desajustes de hidratación, así que las apps son SPA.
  ssr: false,
  // Las clases de la capa se escanean desde su propio CSS (ver el archivo).
  css: [fileURLToPath(new URL('./app/assets/css/leo-client.css', import.meta.url))],
  alias: { '#leo-client': fileURLToPath(new URL('./app', import.meta.url)) },
  runtimeConfig: {
    public: {
      leo: {
        /** `leo-direct` (frontend de Leo ↔ API de Leo) o `bff` (app ↔ su backend con leo_sdk). NUXT_PUBLIC_LEO_TRANSPORT */
        transport: 'leo-direct',
        /** Base de la API (`leo-direct`: la de Leo, ej. http://localhost:8100/api/v1; `bff`: el backend de la app). NUXT_PUBLIC_LEO_API_BASE */
        apiBase: '',
        /** URL pública del backend tal como la valida (`htu`; `PUBLIC_URL` del SDK en `bff`). NUXT_PUBLIC_LEO_PUBLIC_URL */
        publicUrl: '',
        /** `bff`: URL pública del frontend de Leo (enlace "Mi perfil"; vacío = sin enlace). NUXT_PUBLIC_LEO_URL */
        url: '',
        /** `bff`: prefijo de `leo_router` en el backend. NUXT_PUBLIC_LEO_AUTH_PATH */
        authPath: '/auth',
        /** `bff`: ruta del FRONTEND de retorno de login (debe coincidir con la redirect_uri). NUXT_PUBLIC_LEO_CALLBACK_PATH */
        callbackPath: '/auth/callback',
        /** `bff`: inactividad (s) mientras `/auth/me` del SDK no la entregue. NUXT_PUBLIC_LEO_IDLE_TIMEOUT_SECONDS */
        idleTimeoutSeconds: 1800,
        /** Slug de la app actual en Leo (barra superior). NUXT_PUBLIC_LEO_APP_SLUG */
        appSlug: '',
        /** Nombre a mostrar si la app no está en `applications[]`. NUXT_PUBLIC_LEO_APP_NAME */
        appName: '',
        /** Ruta interna de login (transporte `leo-direct`). NUXT_PUBLIC_LEO_LOGIN_PATH */
        loginPath: '/login',
        /** Segundos de aviso antes del cierre por inactividad. */
        idleWarningSeconds: 60,
        /** Mínimo de segundos entre heartbeats de actividad al servidor. */
        heartbeatIntervalSeconds: 60
      }
    }
  }
})
