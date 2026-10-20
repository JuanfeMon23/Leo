// Playground de desarrollo y pruebas de la capa: una app mínima que la
// extiende igual que lo hará cada app del ecosistema (Andromeda + leo-client).
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  extends: ['andromeda', '..']
})
