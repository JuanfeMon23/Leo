// Nombres legibles de los permisos de ajustes para los mensajes de «No tienes permiso para: …».
export default defineNuxtPlugin(() => {
  registerPermissionNames({
    'leo.settings.view': 'Consultar los ajustes del sistema',
    'leo.settings.edit': 'Modificar los ajustes del sistema',
    'leo.settings.edit-security': 'Modificar los ajustes de seguridad'
  })
})
