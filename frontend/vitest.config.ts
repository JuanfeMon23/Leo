import { defineVitestConfig } from '@nuxt/test-utils/config'

export default defineVitestConfig({
  test: {
    // La caché de módulos en disco de Vitest 5 corrompe las corridas repetidas con Nuxt
    // ("Failed to resolve import ./nuxt.js"): se desactiva.
    fsModuleCache: false,
    environment: 'nuxt',
    environmentOptions: {
      nuxt: {
        domEnvironment: 'happy-dom',
        // Las pruebas no dependen de .env: la API es falsa.
        overrides: {
          runtimeConfig: {
            public: {
              leo: {
                transport: 'leo-direct',
                apiBase: 'http://api.test/api/v1',
                publicUrl: 'http://api.test',
                appSlug: 'leo',
                appName: 'Leo',
                loginPath: '/login'
              }
            }
          }
        }
      }
    },
    include: ['tests/**/*.test.ts', 'app/**/*.test.ts', 'layers/**/components/**/*.test.ts', 'layers/**/composables/**/*.test.ts']
  }
})
