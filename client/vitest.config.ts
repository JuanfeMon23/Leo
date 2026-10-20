import { fileURLToPath } from 'node:url'
import { defineVitestConfig } from '@nuxt/test-utils/config'

// Componentes, composables y middleware con auto-imports de Nuxt, sobre el
// playground (Andromeda + esta capa, como lo usará una app).
export default defineVitestConfig({
  test: {
    // La caché de módulos en disco de Vitest 5 corrompe las corridas repetidas con Nuxt: se desactiva.
    fsModuleCache: false,
    environment: 'nuxt',
    environmentOptions: {
      nuxt: {
        rootDir: fileURLToPath(new URL('./.playground', import.meta.url)),
        domEnvironment: 'happy-dom',
        overrides: {
          runtimeConfig: {
            public: {
              leo: {
                transport: 'leo-direct',
                apiBase: 'http://api.test/api/v1',
                publicUrl: 'http://api.test',
                appSlug: 'leo',
                appName: 'Leo',
                loginPath: '/login',
                idleWarningSeconds: 60,
                heartbeatIntervalSeconds: 60
              }
            }
          }
        }
      }
    },
    include: ['app/components/**/*.test.ts', 'app/leo-pages/**/*.test.ts', 'app/composables/**/*.test.ts', 'app/middleware/**/*.test.ts']
  }
})
