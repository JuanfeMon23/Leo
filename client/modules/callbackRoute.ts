import { fileURLToPath } from 'node:url'

/**
 * Registra la página de retorno de login del transporte `bff` en la ruta
 * configurada (`runtimeConfig.public.leo.callbackPath`, por defecto
 * `/auth/callback`). El archivo vive fuera de `pages/` a propósito: así la ruta
 * solo existe en el path configurado y no choca con el del backend de la app
 * cuando comparten origen. Módulo en forma de función (sin `@nuxt/kit`).
 */
export default function leoCallbackRoute(_options: unknown, nuxt: { options: { runtimeConfig: { public: Record<string, any> } }, hook: (name: 'pages:extend', fn: (pages: { name?: string, path: string, file?: string }[]) => void) => void }) {
  const path: string = nuxt.options.runtimeConfig.public.leo?.callbackPath || '/auth/callback'
  nuxt.hook('pages:extend', (pages) => {
    if (pages.some(page => page.name === 'leo-callback')) return
    pages.push({
      name: 'leo-callback',
      path,
      file: fileURLToPath(new URL('../app/leo-pages/callback.vue', import.meta.url))
    })
  })
}
