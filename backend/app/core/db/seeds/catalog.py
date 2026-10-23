"""Catalogo de Leo como app del ecosistema (dogfooding): sus modulos y las
acciones `leo.<modulo>.<verbo>` que protegen sus pantallas y endpoints.

Agregar una accion de Leo = agregarla aqui y volver a correr la semilla (la
crea y se la asigna a `leo-admin`).

Ademas de los permisos, el catalogo registra los tags de **evento** con que
el backend audita (login, logout, rotacion de tokens...): no los chequea
`require_action`, pero toda funcionalidad tiene su tag registrado en Leo. Su
descripcion empieza por "Evento:".
"""

LEO_APP_SLUG = "leo"
LEO_APP_NAME = "Leo"
LEO_APP_DESCRIPTION = "SSO, control de acceso y auditoria central del ecosistema."
LEO_ADMIN_ROLE_SLUG = "leo-admin"
LEO_ADMIN_ROLE_NAME = "Administrador de Leo"

# Roles de la app `leo` que se pueden conceder a una app llamadora (acceso de
# servicio): `leo-patient-provisioner` solo da `leo.users.provision-patient` y
# `leo-self-service-delegate` solo da `leo.users.delegated-self-manage`. Los
# demas roles de Leo (p. ej. `leo-admin`) siguen siendo solo para personas con
# sesion (ver `grant_service_access`).
LEO_PROVISIONER_ROLE_SLUG = "leo-patient-provisioner"
LEO_PROVISIONER_ROLE_NAME = "Aprovisionador de pacientes"
LEO_PROVISION_PATIENT_TAG = "leo.users.provision-patient"
LEO_DELEGATE_ROLE_SLUG = "leo-self-service-delegate"
LEO_DELEGATE_ROLE_NAME = "Delegado de autogestión de usuarios"
LEO_DELEGATED_SELF_MANAGE_TAG = "leo.users.delegated-self-manage"
LEO_SERVICE_GRANTABLE_ROLE_SLUGS = frozenset(
    {LEO_PROVISIONER_ROLE_SLUG, LEO_DELEGATE_ROLE_SLUG}
)

# slug del modulo -> (nombre, {verbo: descripcion})
LEO_MODULES: dict[str, tuple[str, dict[str, str]]] = {
    "applications": (
        "Aplicaciones",
        {
            "view": "Ver aplicaciones, sus modulos y acciones",
            "create": "Registrar aplicaciones, modulos y acciones",
            "edit": "Editar aplicaciones, modulos y acciones",
            "deactivate": "Desactivar o reactivar aplicaciones, modulos y acciones",
            "rotate-secret": "Regenerar el client_secret de una aplicacion",
            "sync-catalog": "Evento: una app sincroniza su catalogo de modulos y "
            "acciones",
            "grant-service-access": "Conceder a una aplicacion roles de otra "
            "aplicacion (acceso entre servicios)",
        },
    ),
    "users": (
        "Usuarios",
        {
            "view": "Ver usuarios",
            "create": "Crear usuarios",
            "edit": "Editar usuarios",
            "deactivate": "Desactivar o reactivar usuarios",
            "unlock": "Desbloquear usuarios bloqueados por intentos fallidos",
            "reset-password": "Asignar una contrasena nueva a un usuario",
            "assign-roles": "Asignar o quitar roles a un usuario",
            "provision-patient": "Crear usuarios con el rol paciente desde una "
            "aplicacion con credencial de servicio",
            "delegated-self-manage": "Editar el perfil y cambiar la contrasena de "
            "un usuario sin permisos de Leo en nombre suyo, desde una aplicacion "
            "con credencial de servicio y el token de acceso del usuario",
        },
    ),
    "roles": (
        "Roles",
        {
            "view": "Ver roles y sus acciones",
            "create": "Crear roles",
            "edit": "Editar roles y sus acciones",
            "deactivate": "Desactivar o reactivar roles",
        },
    ),
    "auth": (
        "Autenticacion",
        {
            "view": "Ver sesiones activas",
            "revoke": "Revocar sesiones",
            "login": "Evento: inicio de sesion (exitoso o fallido)",
            "logout": "Evento: cierre de sesion",
            "lock": "Evento: usuario bloqueado por intentos fallidos",
            "idle-timeout": "Evento: sesion cerrada por inactividad",
            "refresh-reuse": "Evento: reuso de refresh token (familia y sesion "
            "revocadas)",
            "token": "Evento: emision o rotacion de tokens en /token",
            "authorize": "Evento: autorizacion de una app en /authorize",
            "service-token": "Evento: emision de un token de servicio "
            "(client credentials)",
        },
    ),
    "audit": (
        "Auditoria",
        {
            "view": "Consultar eventos de auditoria",
            "export": "Exportar eventos de auditoria",
        },
    ),
}

# tag -> nombre legible en espanol ("Verbo en infinitivo + objeto"; los eventos
# empiezan por "Evento:"). El tag sigue siendo el identificador; el nombre es
# lo que ve quien administra roles. Unico dentro de cada modulo.
LEO_ACTION_NAMES: dict[str, str] = {
    "leo.applications.view": "Consultar aplicaciones",
    "leo.applications.create": "Crear aplicaciones",
    "leo.applications.edit": "Editar aplicaciones",
    "leo.applications.deactivate": "Desactivar y reactivar aplicaciones",
    "leo.applications.rotate-secret": "Rotar el secreto de una aplicación",
    "leo.applications.sync-catalog": "Evento: sincronización de catálogo",
    "leo.applications.grant-service-access": "Conceder acceso entre aplicaciones",
    "leo.users.view": "Consultar usuarios",
    "leo.users.create": "Crear usuarios",
    "leo.users.edit": "Editar usuarios",
    "leo.users.deactivate": "Desactivar y reactivar usuarios",
    "leo.users.unlock": "Desbloquear usuarios",
    "leo.users.reset-password": "Restablecer contraseñas",
    "leo.users.assign-roles": "Asignar roles a usuarios",
    "leo.users.provision-patient": "Aprovisionar pacientes",
    "leo.users.delegated-self-manage": "Delegar la autogestión de usuarios",
    "leo.roles.view": "Consultar roles",
    "leo.roles.create": "Crear roles",
    "leo.roles.edit": "Editar roles",
    "leo.roles.deactivate": "Desactivar y reactivar roles",
    "leo.auth.view": "Consultar sesiones",
    "leo.auth.revoke": "Cerrar sesiones de otros usuarios",
    "leo.auth.login": "Evento: inicio de sesión",
    "leo.auth.logout": "Evento: cierre de sesión",
    "leo.auth.lock": "Evento: bloqueo por intentos fallidos",
    "leo.auth.idle-timeout": "Evento: cierre por inactividad",
    "leo.auth.refresh-reuse": "Evento: reutilización de token",
    "leo.auth.token": "Evento: emisión de tokens",
    "leo.auth.authorize": "Evento: autorización de acceso",
    "leo.auth.service-token": "Evento: emisión de token de servicio",
    "leo.audit.view": "Consultar auditoría",
    "leo.audit.export": "Exportar auditoría",
}


def derived_action_name(verb: str) -> str:
    """Nombre de respaldo de una accion sin nombre propio: el verbo con
    espacios y la primera letra en mayuscula (`rotate-secret` -> `Rotate
    secret`). Es el que rellena la migracion `0003` y el unico que la semilla
    se atreve a reemplazar."""
    return verb.replace("-", " ").capitalize()
