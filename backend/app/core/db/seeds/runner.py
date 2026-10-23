"""Orden de las semillas iniciales; valida la configuracion antes de escribir."""

from dataclasses import dataclass

from sqlalchemy import Connection

from app.core.config import SeedSettings
from app.core.db.seeds.acuarius_app import seed_acuarius_application
from app.core.db.seeds.admin import load_seed_config, seed_admin_user
from app.core.db.seeds.leo_app import (
    seed_leo_delegate_role,
    seed_leo_admin_role,
    seed_leo_application,
    seed_leo_provisioner_role,
)


@dataclass(frozen=True)
class SeedReport:
    admin_username: str
    admin_created: bool


def run_seeds(conn: Connection, settings: SeedSettings) -> SeedReport:
    config = load_seed_config(settings)  # SeedConfigError antes de escribir
    app_id = seed_leo_application(conn, config.frontend_url)
    role_id = seed_leo_admin_role(conn, app_id)
    seed_leo_provisioner_role(conn, app_id)
    seed_leo_delegate_role(conn, app_id)
    seed_acuarius_application(conn)
    created = seed_admin_user(conn, config, role_id)
    return SeedReport(admin_username=config.username, admin_created=created)
