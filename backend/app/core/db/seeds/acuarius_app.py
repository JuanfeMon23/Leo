"""App `acuarius` (portal de pacientes): aplicacion, modulos, acciones y el
rol `paciente`.

Los tags los publica el backend de Acuarius con su `leo_sync`
(`POST /applications/sync-catalog`); sincronizar es idempotente (no duplica
ni pisa lo editado). Se registran aqui tambien para que el rol `paciente`
exista con sus permisos desde la primera semilla, de modo que el
aprovisionamiento de pacientes (`POST /users/service/patients`) funcione sin
esperar a la primera sincronizacion.

El `client_secret` inicial es aleatorio y solo se guarda su hash (nadie lo
conoce): para usarlo, regenerarlo desde la administracion de Leo.
"""

import hashlib
import secrets
from uuid import UUID

from sqlalchemy import Connection, literal, select
from sqlalchemy.dialects.postgresql import insert

from app.modules.applications.models import Action, Application, AppModule
from app.modules.roles.models import Role, RoleAction

ACUARIUS_APP_SLUG = "acuarius"
ACUARIUS_APP_NAME = "Acuarius"
ACUARIUS_APP_DESCRIPTION = "Portal de pacientes: resultados y grupo familiar."
ACUARIUS_BASE_URL = "http://localhost:3300"
ACUARIUS_REDIRECT_URIS = ["http://localhost:3300/auth/callback"]
PATIENT_ROLE_SLUG = "paciente"
PATIENT_ROLE_NAME = "Paciente"

# slug del modulo -> (nombre, {verbo: (nombre legible, descripcion)})
ACUARIUS_MODULES: dict[str, tuple[str, dict[str, tuple[str, str]]]] = {
    "results": (
        "Resultados",
        {
            "view": ("Consultar resultados", "Ver los resultados propios"),
            "download": ("Descargar resultados", "Descargar los resultados propios"),
        },
    ),
    "family": (
        "Grupo familiar",
        {
            "view": ("Consultar grupo familiar", "Ver el grupo familiar"),
            "invite": ("Invitar familiares", "Invitar a un familiar al grupo"),
            "respond": (
                "Responder invitaciones",
                "Aceptar o rechazar invitaciones de grupo familiar",
            ),
            "manage": (
                "Gestionar grupo familiar",
                "Administrar los miembros y permisos del grupo familiar",
            ),
        },
    ),
}


def seed_acuarius_application(conn: Connection) -> UUID:
    """Registra la app `acuarius`, sus modulos/acciones y el rol `paciente`
    (con todas sus acciones) si faltan; devuelve el id del rol."""
    apps = Application.__table__
    conn.execute(
        insert(apps)
        .values(
            slug=ACUARIUS_APP_SLUG,
            name=ACUARIUS_APP_NAME,
            description=ACUARIUS_APP_DESCRIPTION,
            base_url=ACUARIUS_BASE_URL,
            redirect_uris=ACUARIUS_REDIRECT_URIS,
            client_id=ACUARIUS_APP_SLUG,
            client_secret_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        )
        .on_conflict_do_nothing(index_elements=["slug"])
    )
    app_id = conn.scalar(select(apps.c.id).where(apps.c.slug == ACUARIUS_APP_SLUG))

    modules, actions = AppModule.__table__, Action.__table__
    for module_slug, (module_name, verbs) in ACUARIUS_MODULES.items():
        conn.execute(
            insert(modules)
            .values(application_id=app_id, slug=module_slug, name=module_name)
            .on_conflict_do_nothing(index_elements=["application_id", "slug"])
        )
        module_id = conn.scalar(
            select(modules.c.id).where(
                modules.c.application_id == app_id, modules.c.slug == module_slug
            )
        )
        for verb, (name, description) in verbs.items():
            conn.execute(
                insert(actions)
                .values(
                    application_id=app_id,
                    module_id=module_id,
                    verb=verb,
                    tag=f"{ACUARIUS_APP_SLUG}.{module_slug}.{verb}",
                    name=name,
                    description=description,
                )
                .on_conflict_do_nothing(index_elements=["tag"])
            )

    roles = Role.__table__
    conn.execute(
        insert(roles)
        .values(application_id=app_id, slug=PATIENT_ROLE_SLUG, name=PATIENT_ROLE_NAME)
        .on_conflict_do_nothing(index_elements=["application_id", "slug"])
    )
    role_id = conn.scalar(
        select(roles.c.id).where(
            roles.c.application_id == app_id, roles.c.slug == PATIENT_ROLE_SLUG
        )
    )
    conn.execute(
        insert(RoleAction.__table__)
        .from_select(
            ["role_id", "action_id", "application_id"],
            select(literal(role_id), actions.c.id, actions.c.application_id).where(
                actions.c.application_id == app_id
            ),
        )
        .on_conflict_do_nothing(index_elements=["role_id", "action_id"])
    )
    return role_id
