"""Semilla inicial: app `leo` con sus modulos y acciones `leo.*`, rol
`leo-admin` con todas y el administrador desde `LEO_ADMIN_*`. Idempotente;
falla con mensaje claro si faltan variables o la contrasena es debil."""

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import SeedSettings
from app.core.db.seeds.admin import SeedConfigError
from app.core.db.seeds.catalog import (
    LEO_ACTION_NAMES,
    LEO_ADMIN_ROLE_SLUG,
    LEO_APP_SLUG,
    LEO_MODULES,
)
from app.core.db.seeds.runner import run_seeds
from app.core.security.passwords import password_weaknesses, verify_password

from .conftest import unique

STRONG_PASSWORD = "Correcto-Caballo-9-Bateria"
REQUIRED_VARS = (
    "LEO_FRONTEND_URL",
    "LEO_ADMIN_USERNAME",
    "LEO_ADMIN_EMAIL",
    "LEO_ADMIN_PASSWORD",
    "LEO_ADMIN_DOCUMENT_TYPE",
    "LEO_ADMIN_DOCUMENT_NUMBER",
)


def _settings(**overrides: object) -> SeedSettings:
    username = unique("admin")
    values: dict[str, object] = {
        "frontend_url": "http://localhost:3100",
        "admin_username": username,
        "admin_email": f"{username}@example.com",
        "admin_password": SecretStr(STRONG_PASSWORD),
        "admin_document_type": "CC",
        "admin_document_number": "1000000001",
        **overrides,
    }
    return SeedSettings(_env_file=None, **values)


@pytest.fixture(autouse=True)
def _sin_variables_leo_en_el_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    """Los tests no dependen de `.env` ni de variables `LEO_*` del proceso."""
    for name in (*REQUIRED_VARS, "LEO_ADMIN_FIRST_NAME", "LEO_ADMIN_LAST_NAME"):
        monkeypatch.delenv(name, raising=False)


async def _seed(conn: AsyncConnection, settings: SeedSettings) -> None:
    await conn.run_sync(lambda sync: run_seeds(sync, settings))


async def _scalar(conn: AsyncConnection, sql: str, **params: object) -> object:
    return (await conn.execute(text(sql), params)).scalar_one()


async def _snapshot(conn: AsyncConnection) -> tuple:
    counts = []
    for table in (
        "applications",
        "app_modules",
        "actions",
        "roles",
        "role_actions",
        "users",
        "user_roles",
    ):
        counts.append(await _scalar(conn, f"SELECT count(*) FROM {table}"))
    hashes = (await conn.execute(text("SELECT password_hash FROM users"))).all()
    return tuple(counts), sorted(hashes)


async def test_semilla_registra_app_leo_con_sus_modulos_y_acciones(
    conn: AsyncConnection,
) -> None:
    await _seed(conn, _settings())
    rows = (
        await conn.execute(
            text(
                "SELECT m.slug, ac.tag FROM actions ac "
                "JOIN app_modules m ON m.id = ac.module_id "
                "JOIN applications a ON a.id = ac.application_id "
                "WHERE a.slug = :slug"
            ),
            {"slug": LEO_APP_SLUG},
        )
    ).all()
    expected = {
        f"leo.{module}.{verb}"
        for module, (_, verbs) in LEO_MODULES.items()
        for verb in verbs
    }
    assert {module for module, _ in rows} == {
        "applications",
        "users",
        "roles",
        "auth",
        "audit",
    }
    assert {tag for _, tag in rows} == expected
    secret_hash = await _scalar(
        conn,
        "SELECT client_secret_hash FROM applications WHERE slug = :s",
        s=LEO_APP_SLUG,
    )
    assert len(secret_hash) == 64


async def test_rol_leo_admin_tiene_todas_las_acciones_leo_y_es_del_admin(
    conn: AsyncConnection,
) -> None:
    settings = _settings()
    await _seed(conn, settings)
    missing = await _scalar(
        conn,
        "SELECT count(*) FROM actions ac JOIN applications a "
        "ON a.id = ac.application_id WHERE a.slug = 'leo' AND NOT EXISTS ("
        "SELECT 1 FROM role_actions ra JOIN roles r ON r.id = ra.role_id "
        "WHERE r.slug = :role AND ra.action_id = ac.id)",
        role=LEO_ADMIN_ROLE_SLUG,
    )
    assert missing == 0
    assigned = await _scalar(
        conn,
        "SELECT count(*) FROM user_roles ur JOIN users u ON u.id = ur.user_id "
        "JOIN roles r ON r.id = ur.role_id WHERE u.username = :u AND r.slug = :r",
        u=settings.admin_username,
        r=LEO_ADMIN_ROLE_SLUG,
    )
    assert assigned == 1


async def test_admin_queda_con_hash_argon2id_de_su_contrasena(
    conn: AsyncConnection,
) -> None:
    settings = _settings()
    await _seed(conn, settings)
    stored = await _scalar(
        conn,
        "SELECT password_hash FROM users WHERE username = :u",
        u=settings.admin_username,
    )
    assert stored.startswith("$argon2id$")
    assert STRONG_PASSWORD not in stored
    assert verify_password(stored, STRONG_PASSWORD)


async def test_semilla_es_idempotente(conn: AsyncConnection) -> None:
    settings = _settings()
    await _seed(conn, settings)
    first = await _snapshot(conn)
    await _seed(conn, settings)
    assert await _snapshot(conn) == first


async def test_semilla_sin_variables_falla_nombrando_las_que_faltan(
    conn: AsyncConnection,
) -> None:
    with pytest.raises(SeedConfigError) as exc:
        await _seed(conn, SeedSettings(_env_file=None))
    for name in REQUIRED_VARS:
        assert name in str(exc.value)
    assert await _scalar(conn, "SELECT count(*) FROM applications") == 0


async def test_variable_en_blanco_cuenta_como_faltante(conn: AsyncConnection) -> None:
    with pytest.raises(SeedConfigError, match="LEO_ADMIN_EMAIL"):
        await _seed(conn, _settings(admin_email="   "))


@pytest.mark.parametrize(
    "password",
    [
        "Corta-1",  # menos de 12
        "todo-minusculas-123",  # sin mayuscula
        "TODO-MAYUSCULAS-123",  # sin minuscula
        "Sin-Digitos-Aqui",  # sin digito
        "SinSimbolos12345",  # sin simbolo
    ],
)
async def test_semilla_rechaza_contrasena_debil_sin_escribir_nada(
    conn: AsyncConnection, password: str
) -> None:
    with pytest.raises(SeedConfigError, match="LEO_ADMIN_PASSWORD"):
        await _seed(conn, _settings(admin_password=SecretStr(password)))
    assert await _scalar(conn, "SELECT count(*) FROM users") == 0


async def test_semilla_rechaza_tipo_de_documento_desconocido(
    conn: AsyncConnection,
) -> None:
    with pytest.raises(SeedConfigError, match="LEO_ADMIN_DOCUMENT_TYPE"):
        await _seed(conn, _settings(admin_document_type="XX"))


def test_contrasena_que_contiene_el_usuario_ya_no_es_debil() -> None:
    assert password_weaknesses("Juanfe-Seguro-2026!", username="juanfe") == []


def test_contrasena_fuerte_no_tiene_debilidades() -> None:
    assert password_weaknesses(STRONG_PASSWORD, username="admin") == []


# Tags con que el backend audita eventos (no son permisos que se chequeen,
# pero toda funcionalidad tiene su tag registrado en Leo).
EVENT_TAGS = {
    "leo.auth.login",
    "leo.auth.logout",
    "leo.auth.lock",
    "leo.auth.idle-timeout",
    "leo.auth.refresh-reuse",
    "leo.auth.token",
    "leo.auth.authorize",
    "leo.applications.sync-catalog",
}


async def test_semilla_registra_los_tags_de_evento_auditados(
    conn: AsyncConnection,
) -> None:
    await _seed(conn, _settings())
    rows = await conn.execute(
        text(
            "SELECT ac.tag FROM actions ac JOIN roles r "
            "ON r.application_id = ac.application_id JOIN role_actions ra "
            "ON ra.role_id = r.id AND ra.action_id = ac.id "
            "WHERE r.slug = :role AND ac.tag = ANY(:tags)"
        ),
        {"role": LEO_ADMIN_ROLE_SLUG, "tags": list(EVENT_TAGS)},
    )
    assert {r[0] for r in rows} == EVENT_TAGS


async def test_semilla_agrega_acciones_nuevas_del_catalogo_sin_duplicar(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una BD sembrada con un catalogo anterior recibe las acciones nuevas
    (y su asignacion a `leo-admin`) al volver a correr la semilla."""
    settings = _settings()
    old_catalog = {
        module: (name, {v: d for v, d in verbs.items() if v != "login"})
        for module, (name, verbs) in LEO_MODULES.items()
    }
    monkeypatch.setattr("app.core.db.seeds.leo_app.LEO_MODULES", old_catalog)
    await _seed(conn, settings)
    assert (
        await _scalar(conn, "SELECT count(*) FROM actions WHERE tag = 'leo.auth.login'")
        == 0
    )
    before = await _scalar(conn, "SELECT count(*) FROM actions")

    monkeypatch.setattr("app.core.db.seeds.leo_app.LEO_MODULES", LEO_MODULES)
    await _seed(conn, settings)
    await _seed(conn, settings)

    assert await _scalar(conn, "SELECT count(*) FROM actions") == before + 1
    assigned = await _scalar(
        conn,
        "SELECT count(*) FROM role_actions ra JOIN actions ac ON ac.id = ra.action_id "
        "JOIN roles r ON r.id = ra.role_id "
        "WHERE ac.tag = 'leo.auth.login' AND r.slug = :role",
        role=LEO_ADMIN_ROLE_SLUG,
    )
    assert assigned == 1


# --- credenciales de servicio (acceso entre aplicaciones) ---

GRANT_TAG = "leo.applications.grant-service-access"
SERVICE_TOKEN_TAG = "leo.auth.service-token"


async def test_semilla_agrega_las_acciones_de_servicio_sin_duplicar(
    conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una BD sembrada con el catalogo anterior recibe las dos acciones de
    credenciales de servicio, asignadas a `leo-admin`, sin duplicar."""
    settings = _settings()
    old_catalog = {
        module: (
            name,
            {
                v: d
                for v, d in verbs.items()
                if v not in ("grant-service-access", "service-token")
            },
        )
        for module, (name, verbs) in LEO_MODULES.items()
    }
    monkeypatch.setattr("app.core.db.seeds.leo_app.LEO_MODULES", old_catalog)
    await _seed(conn, settings)
    tags = [GRANT_TAG, SERVICE_TOKEN_TAG]
    count_sql = "SELECT count(*) FROM actions WHERE tag = ANY(:tags)"
    assert await _scalar(conn, count_sql, tags=tags) == 0

    monkeypatch.setattr("app.core.db.seeds.leo_app.LEO_MODULES", LEO_MODULES)
    await _seed(conn, settings)
    await _seed(conn, settings)

    assert await _scalar(conn, count_sql, tags=tags) == 2
    assigned = await _scalar(
        conn,
        "SELECT count(*) FROM role_actions ra JOIN actions ac ON ac.id = ra.action_id "
        "JOIN roles r ON r.id = ra.role_id "
        "WHERE ac.tag = ANY(:tags) AND r.slug = :role",
        tags=tags,
        role=LEO_ADMIN_ROLE_SLUG,
    )
    assert assigned == 2


async def test_acciones_de_servicio_tienen_nombre_y_modulo_correctos(
    conn: AsyncConnection,
) -> None:
    await _seed(conn, _settings())
    rows = (
        await conn.execute(
            text(
                "SELECT ac.tag, ac.name, m.slug, ac.description FROM actions ac "
                "JOIN app_modules m ON m.id = ac.module_id WHERE ac.tag = ANY(:tags)"
            ),
            {"tags": [GRANT_TAG, SERVICE_TOKEN_TAG]},
        )
    ).all()
    by_tag = {r.tag: r for r in rows}
    assert by_tag[GRANT_TAG].name == "Conceder acceso entre aplicaciones"
    assert by_tag[GRANT_TAG].slug == "applications"
    assert not by_tag[GRANT_TAG].description.startswith("Evento:")
    assert by_tag[SERVICE_TOKEN_TAG].name == "Evento: emisión de token de servicio"
    assert by_tag[SERVICE_TOKEN_TAG].slug == "auth"
    assert by_tag[SERVICE_TOKEN_TAG].description.startswith("Evento:")


async def test_semilla_no_pisa_el_nombre_editado_de_una_accion_de_servicio(
    conn: AsyncConnection,
) -> None:
    settings = _settings()
    await _seed(conn, settings)
    await conn.execute(
        text("UPDATE actions SET name = 'Mi nombre' WHERE tag = :t"), {"t": GRANT_TAG}
    )
    await _seed(conn, settings)
    assert (await _names(conn))[GRANT_TAG] == "Mi nombre"


# --- nombres legibles de las acciones ---


async def _names(conn: AsyncConnection) -> dict[str, str]:
    rows = await conn.execute(
        text(
            "SELECT ac.tag, ac.name FROM actions ac JOIN applications a "
            "ON a.id = ac.application_id WHERE a.slug = :slug"
        ),
        {"slug": LEO_APP_SLUG},
    )
    return {tag: name for tag, name in rows}


async def test_toda_accion_leo_queda_con_su_nombre_del_catalogo(
    conn: AsyncConnection,
) -> None:
    await _seed(conn, _settings())
    names = await _names(conn)
    assert names == LEO_ACTION_NAMES
    assert len(names) == 30
    assert len(set(names.values())) == 30


def test_catalogo_nombra_exactamente_las_acciones_de_leo() -> None:
    tags = {
        f"leo.{module}.{verb}"
        for module, (_, verbs) in LEO_MODULES.items()
        for verb in verbs
    }
    assert set(LEO_ACTION_NAMES) == tags


def test_nombres_de_eventos_empiezan_por_evento() -> None:
    for module, (_, verbs) in LEO_MODULES.items():
        for verb, description in verbs.items():
            tag = f"leo.{module}.{verb}"
            assert description.startswith("Evento:") == LEO_ACTION_NAMES[
                tag
            ].startswith("Evento:")


async def test_semilla_no_pisa_un_nombre_editado(conn: AsyncConnection) -> None:
    settings = _settings()
    await _seed(conn, settings)
    await conn.execute(
        text("UPDATE actions SET name = 'Mi nombre' WHERE tag = 'leo.users.view'")
    )
    await _seed(conn, settings)
    assert (await _names(conn))["leo.users.view"] == "Mi nombre"


async def test_semilla_reemplaza_el_nombre_derivado_por_la_migracion(
    conn: AsyncConnection,
) -> None:
    settings = _settings()
    await _seed(conn, settings)
    await conn.execute(
        text(
            "UPDATE actions SET name = 'Reset password' WHERE tag = 'leo.users.reset-password'"
        )
    )
    await _seed(conn, settings)
    assert (await _names(conn))["leo.users.reset-password"] == "Restablecer contraseñas"
