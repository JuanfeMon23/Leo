export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  // Sistema de diseño compartido (Andromeda) + sesión/permisos del ecosistema (leo-client).
  // Andromeda va primero: los componentes de leo-client usan sus Ui* y tokens.
  extends: ['andromeda', '../client'],
  // Utilidades de Tailwind de las layers de módulo y del núcleo (ver el archivo).
  css: ['~/assets/css/leo-admin.css']
  // Configuración de Leo (API, URL pública, slug y nombre de la app): variables
  // NUXT_PUBLIC_LEO_* de frontend/.env (ver .env.example); leo-client define las claves.
})
