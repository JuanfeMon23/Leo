"""App `leo` (dogfooding): aplicacion, modulos, acciones `leo.*` y el rol
`leo-admin` con todas sus acciones."""

import hashlib
import secrets
from uuid import UUID

from sqlalchemy import Connection, literal, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.db.seeds.catalog import (
    LEO_ACTION_NAMES,
    LEO_ADMIN_ROLE_NAME,
    LEO_ADMIN_ROLE_SLUG,
    LEO_APP_DESCRIPTION,
    LEO_APP_NAME,
    LEO_APP_SLUG,
    LEO_MODULES,
    LEO_PROVISION_PATIENT_TAG,
    LEO_PROVISIONER_ROLE_NAME,
    LEO_PROVISIONER_ROLE_SLUG,
    derived_action_name,
)
from app.modules.applications.models import Action, Application, AppModule
from app.modules.roles.models import Role, RoleAction


def seed_leo_application(conn: Connection, frontend_url: str) -> UUID:
    """Registra la app `leo`, sus modulos y acciones si faltan; devuelve su id.

    El client_secret inicial es aleatorio y solo se guarda su hash (nadie lo
    conoce): para usarlo, se regenera desde la administracion de Leo.
    """
    apps = Application.__table__
    conn.execute(
        insert(apps)
        .values(
            slug=LEO_APP_SLUG,
            name=LEO_APP_NAME,
            description=LEO_APP_DESCRIPTION,
            base_url=frontend_url,
            client_id=LEO_APP_SLUG,
            client_secret_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        )
        .on_conflict_do_nothing(index_elements=["slug"])
    )
    app_id = conn.scalar(select(apps.c.id).where(apps.c.slug == LEO_APP_SLUG))

    modules, actions = AppModule.__table__, Action.__table__
    for module_slug, (module_name, verbs) in LEO_MODULES.items():
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
        for verb, description in verbs.items():
            tag = f"{LEO_APP_SLUG}.{module_slug}.{verb}"
            name = LEO_ACTION_NAMES.get(tag, derived_action_name(verb))
            conn.execute(
                insert(actions)
                .values(
                    application_id=app_id,
                    module_id=module_id,
                    verb=verb,
                    tag=tag,
                    name=name,
                    description=description,
                )
                .on_conflict_do_nothing(index_elements=["tag"])
            )
            # Solo se reemplaza el nombre de respaldo que dejo la migracion:
            # un nombre distinto lo puso un admin y no se pisa.
            conn.execute(
                update(actions)
                .where(
                    actions.c.tag == tag, actions.c.name == derived_action_name(verb)
                )
                .values(name=name)
            )
    return app_id


def seed_leo_admin_role(conn: Connection, app_id: UUID) -> UUID:
    """Crea `leo-admin` si falta y le asigna toda accion de la app `leo` que
    aun no tenga; devuelve su id."""
    roles, actions = Role.__table__, Action.__table__
    conn.execute(
        insert(roles)
        .values(
            application_id=app_id, slug=LEO_ADMIN_ROLE_SLUG, name=LEO_ADMIN_ROLE_NAME
        )
        .on_conflict_do_nothing(index_elements=["application_id", "slug"])
    )
    role_id = conn.scalar(
        select(roles.c.id).where(
            roles.c.application_id == app_id, roles.c.slug == LEO_ADMIN_ROLE_SLUG
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


def seed_leo_provisioner_role(conn: Connection, app_id: UUID) -> UUID:
    """Crea `leo-patient-provisioner` (rol concedible a una app llamadora) con
    la unica accion `leo.users.provision-patient`; devuelve su id."""
    roles, actions = Role.__table__, Action.__table__
    conn.execute(
        insert(roles)
        .values(
            application_id=app_id,
            slug=LEO_PROVISIONER_ROLE_SLUG,
            name=LEO_PROVISIONER_ROLE_NAME,
        )
        .on_conflict_do_nothing(index_elements=["application_id", "slug"])
    )
    role_id = conn.scalar(
        select(roles.c.id).where(
            roles.c.application_id == app_id, roles.c.slug == LEO_PROVISIONER_ROLE_SLUG
        )
    )
    conn.execute(
        insert(RoleAction.__table__)
        .from_select(
            ["role_id", "action_id", "application_id"],
            select(literal(role_id), actions.c.id, actions.c.application_id).where(
                actions.c.tag == LEO_PROVISION_PATIENT_TAG
            ),
        )
        .on_conflict_do_nothing(index_elements=["role_id", "action_id"])
    )
    return role_id
