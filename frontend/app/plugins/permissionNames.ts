// Nombres legibles de los permisos para los mensajes de «No tienes permiso para: …»,
// derivados del contrato generado por el backend.
export default defineNuxtPlugin(() => {
  registerPermissionNames(PERMISSION_NAMES)
})
