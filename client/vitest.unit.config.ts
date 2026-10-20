import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

// Lógica pura de la capa (`app/lib`, no auto-importada): DPoP, permisos,
// inactividad, errores y transporte. Entorno node, sin Nuxt; WebCrypto y
// BroadcastChannel son globales de Node 24.
export default defineConfig({
  resolve: {
    alias: {
      '#andromeda': fileURLToPath(new URL('./node_modules/andromeda/app', import.meta.url))
    }
  },
  test: { environment: 'node', include: ['app/lib/**/*.test.ts'] }
})
