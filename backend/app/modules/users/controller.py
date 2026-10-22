"""Casos de uso de `users`: CRUD, bloqueo, contrasena, roles, y la
verificacion de credenciales del login (la usa `auth`).

Reglas:
- Contrasena con la politica compartida con la semilla
  (`password_weaknesses`), guardada con argon2id; rehash si cambian los
  parametros.
- Desactivar un usuario o restablecer su contrasena revoca sus sesiones
  (invalidacion inmediata).
- Un usuario no se desactiva a si mismo.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.audit import Actor, diff, snapshot
from app.core.config import get_settings
from app.core.exceptions import (
    AppError,
    ConflictError,
    DuplicateValueError,
    TooManyRequestsError,
    UnauthorizedError,
    ValidationAppError,
    not_found,
)
from app.core.pagination import Pagination, get_or_404, paginate
from app.core.rate_limit import SlidingWindowLimiter
from app.core.schemas import Page
from app.core.security.passwords import (
    burn_verification_time,
    hash_password,
    needs_rehash,
    password_weaknesses,
    verify_password,
)
from app.core.service_authz import ServicePrincipal
from app.modules import audit, auth, roles
from app.modules.users import repository
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import (
    PasswordReset,
    PatientProvision,
    PatientRead,
    ProfileUpdate,
    UserCreate,
    UserDetail,
    UserRead,
    UserRoleRead,
    UserRolesAdd,
    UserUpdate,
)

USER_FIELDS = (
    "username",
    "email",
    "document_type",
    "document_number",
    "first_name",
    "last_name",
    "is_active",
    "failed_login_attempts",
    "locked_until",
)
PROFILE_FIELDS = ("first_name", "last_name", "email")
SELF_SERVICE_REASON = "autogestión"
_USER = "un usuario"


@dataclass(frozen=True)
class UserIdentity:
    id: UUID
    username: str
    email: str
    first_name: str
    last_name: str
    is_active: bool

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


def _identity(user: User) -> UserIdentity:
    return UserIdentity(
        user.id,
        user.username,
        user.email,
        user.first_name,
        user.last_name,
        user.is_active,
    )


class LoginOutcome(StrEnum):
    OK = "ok"
    INVALID = "invalid"  # usuario inexistente o contrasena incorrecta
    LOCKED = "locked"  # bloqueado por intentos fallidos
    INACTIVE = "inactive"  # contrasena correcta pero usuario desactivado


@dataclass(frozen=True)
class LoginCheck:
    outcome: LoginOutcome
    user: UserIdentity | None = None
    locked_until: datetime | None = None
    just_locked: bool = False


# --- interfaz publica para otros modulos ---


async def get_identity(session: AsyncSession, user_id: UUID) -> UserIdentity | None:
    user = await session.get(User, user_id)
    return _identity(user) if user else None


async def check_credentials(
    session: AsyncSession,
    login: str,
    password: str,
    *,
    max_failed_attempts: int,
    lock_minutes: int,
) -> LoginCheck:
    """Verifica usuario/email + contrasena y actualiza el contador de
    intentos, el bloqueo y `last_login_at` (sin commit). Siempre calcula un
    hash argon2 (real o ficticio) para que el tiempo no revele si existe."""
    user = await repository.find_by_login(session, login)
    if user is None:
        burn_verification_time(password)
        return LoginCheck(LoginOutcome.INVALID)
    now = clock.now()
    if user.locked_until is not None and user.locked_until > now:
        burn_verification_time(password)
        return LoginCheck(LoginOutcome.LOCKED, _identity(user), user.locked_until)
    if not verify_password(user.password_hash, password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= max_failed_attempts:
            user.locked_until = now + timedelta(minutes=lock_minutes)
            user.failed_login_attempts = 0
            await session.flush()
            return LoginCheck(
                LoginOutcome.LOCKED,
                _identity(user),
                user.locked_until,
                just_locked=True,
            )
        await session.flush()
        return LoginCheck(LoginOutcome.INVALID, _identity(user))
    if not user.is_active:
        return LoginCheck(LoginOutcome.INACTIVE, _identity(user))
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    await session.flush()
    return LoginCheck(LoginOutcome.OK, _identity(user))


# --- CRUD ---


async def list_users(
    session: AsyncSession, q: str | None, active: bool | None, pagination: Pagination
) -> Page[UserRead]:
    stmt = repository.list_statement(q, active)
    return await paginate(session, stmt, pagination, UserRead, User.username)


async def _detail(session: AsyncSession, user: User) -> UserDetail:
    role_ids = await repository.role_ids_of(session, user.id)
    briefs = await roles.roles_brief(session, role_ids)
    return UserDetail(
        **UserRead.model_validate(user).model_dump(),
        roles=[
            UserRoleRead(
                id=b.id,
                application_id=b.application_id,
                slug=b.slug,
                name=b.name,
                is_active=b.is_active,
            )
            for b in sorted(briefs.values(), key=lambda b: b.slug)
        ],
    )


async def get_user(session: AsyncSession, user_id: UUID) -> UserDetail:
    return await _detail(session, await get_or_404(session, User, user_id, _USER))


def _check_password(password: str, username: str, email: str) -> None:
    weaknesses = password_weaknesses(password, username=username, email=email)
    if weaknesses:
        raise ValidationAppError(
            f"La contraseña es débil: {'; '.join(weaknesses)}.",
            {"password": weaknesses},
            code="weak_password",
        )


async def _check_unique(
    session: AsyncSession,
    *,
    email: str | None,
    document: tuple | None,
    exclude_id: UUID | None = None,
) -> None:
    if email is not None and await repository.email_taken(session, email, exclude_id):
        raise DuplicateValueError(
            entity=_USER, field="email", field_label="el email", value=email
        )
    if document is not None and await repository.document_taken(
        session, document[0], document[1], exclude_id
    ):
        raise DuplicateValueError(
            entity=_USER,
            field="document_number",
            field_label="el documento",
            value=f"{document[0]} {document[1]}",
        )


async def create_user(
    session: AsyncSession, data: UserCreate, actor: Actor
) -> UserRead:
    if await repository.username_taken(session, data.username):
        raise DuplicateValueError(
            entity=_USER,
            field="username",
            field_label="el usuario",
            value=data.username,
        )
    await _check_unique(
        session, email=data.email, document=(data.document_type, data.document_number)
    )
    _check_password(data.password, data.username, data.email)
    user = User(
        **data.model_dump(exclude={"password"}),
        password_hash=hash_password(data.password),
    )
    session.add(user)
    await audit.record_change(
        session, actor, "leo.users.create", "user", user, None, USER_FIELDS
    )
    await session.commit()
    return UserRead.model_validate(user)


async def update_user(
    session: AsyncSession, user_id: UUID, data: UserUpdate, actor: Actor
) -> UserRead:
    user = await get_or_404(session, User, user_id, _USER)
    changes = data.model_dump(exclude_unset=True)
    document = (
        changes.get("document_type", user.document_type),
        changes.get("document_number", user.document_number),
    )
    await _check_unique(
        session,
        email=changes.get("email"),
        document=document
        if {"document_type", "document_number"} & changes.keys()
        else None,
        exclude_id=user.id,
    )
    before = snapshot(user, USER_FIELDS)
    for name, value in changes.items():
        setattr(user, name, value)
    await audit.record_change(
        session, actor, "leo.users.edit", "user", user, before, USER_FIELDS
    )
    await session.commit()
    return UserRead.model_validate(user)


async def set_user_active(
    session: AsyncSession, user_id: UUID, active: bool, actor: Actor
) -> UserRead:
    user = await get_or_404(session, User, user_id, _USER)
    if not active and user.id == actor.user_id:
        raise ConflictError(
            "No puedes desactivar tu propio usuario.", code="self_deactivation"
        )
    before = snapshot(user, USER_FIELDS)
    user.is_active = active
    await audit.record_change(
        session, actor, "leo.users.deactivate", "user", user, before, USER_FIELDS
    )
    if not active:
        await auth.revoke_user_sessions(session, user.id, "user-deactivated")
    await session.commit()
    return UserRead.model_validate(user)


async def unlock_user(session: AsyncSession, user_id: UUID, actor: Actor) -> UserRead:
    user = await get_or_404(session, User, user_id, _USER)
    before = snapshot(user, USER_FIELDS)
    user.failed_login_attempts = 0
    user.locked_until = None
    await audit.record_change(
        session, actor, "leo.users.unlock", "user", user, before, USER_FIELDS
    )
    await session.commit()
    return UserRead.model_validate(user)


async def reset_password(
    session: AsyncSession, user_id: UUID, data: PasswordReset, actor: Actor
) -> UserRead:
    user = await get_or_404(session, User, user_id, _USER)
    _check_password(data.password, user.username, user.email)
    before = snapshot(user, USER_FIELDS)
    user.password_hash = hash_password(data.password)
    user.failed_login_attempts = 0
    user.locked_until = None
    await session.flush()
    await session.refresh(user)
    await audit.record_event(
        session,
        actor.entry(
            "leo.users.reset-password",
            entity_type="user",
            entity_id=str(user.id),
            changes=diff(before, snapshot(user, USER_FIELDS)),
            reason="Contraseña restablecida; se cerraron sus sesiones.",
        ),
    )
    await auth.revoke_user_sessions(session, user.id, "admin")
    await session.commit()
    return UserRead.model_validate(user)


# --- autogestion (el propio usuario; la ruta vive en `auth`) ---
#
# Se reutilizan los tags `leo.users.edit` y `leo.users.reset-password` solo
# como ACCION AUDITADA (para que el historial muestre el mismo tipo de cambio
# sea un admin o la propia persona). NO se chequean como permiso: la
# autogestion solo exige la sesion SSO, y `reason="autogestión"` la distingue.


async def update_own_profile(
    session: AsyncSession, user_id: UUID, data: ProfileUpdate, actor: Actor
) -> bool:
    """Cambia nombres/correo del propio usuario. True si hubo cambios reales;
    si no, no escribe ni audita. Sin commit."""
    user = await get_or_404(session, User, user_id, _USER)
    changes = {
        name: value
        for name, value in data.model_dump(exclude_unset=True).items()
        if getattr(user, name) != value
    }
    if not changes:
        return False
    await _check_unique(
        session, email=changes.get("email"), document=None, exclude_id=user.id
    )
    before = snapshot(user, PROFILE_FIELDS)
    for name, value in changes.items():
        setattr(user, name, value)
    await session.flush()
    await session.refresh(user)
    await audit.record_event(
        session,
        actor.entry(
            "leo.users.edit",
            entity_type="user",
            entity_id=str(user.id),
            changes=diff(before, snapshot(user, PROFILE_FIELDS)),
            reason=SELF_SERVICE_REASON,
        ),
    )
    return True


async def change_own_password(
    session: AsyncSession,
    user_id: UUID,
    current_password: str,
    new_password: str,
    actor: Actor,
) -> None:
    """Cambia la contrasena del propio usuario: exige la actual, aplica la
    politica compartida, rechaza reusar la actual y reinicia intentos y
    bloqueo. Sin commit ni revocar sesiones (lo hace quien llama). Lanza
    `UnauthorizedError(invalid_credentials)` si la actual no coincide."""
    user = await get_or_404(session, User, user_id, _USER)
    if not verify_password(user.password_hash, current_password):
        raise UnauthorizedError(
            "La contraseña actual no es correcta.", code="invalid_credentials"
        )
    _check_password(new_password, user.username, user.email)
    if verify_password(user.password_hash, new_password):
        raise ValidationAppError(
            "La contraseña nueva debe ser distinta de la actual.",
            code="same_password",
        )
    before = snapshot(user, USER_FIELDS)
    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    await session.flush()
    await session.refresh(user)
    await audit.record_event(
        session,
        actor.entry(
            "leo.users.reset-password",
            entity_type="user",
            entity_id=str(user.id),
            changes=diff(before, snapshot(user, USER_FIELDS)),
            reason=SELF_SERVICE_REASON,
        ),
    )


async def add_roles(
    session: AsyncSession, user_id: UUID, data: UserRolesAdd, actor: Actor
) -> UserDetail:
    user = await get_or_404(session, User, user_id, _USER)
    requested = list(dict.fromkeys(data.role_ids))
    briefs = await roles.roles_brief(session, requested)
    missing = [str(i) for i in requested if i not in briefs]
    if missing:
        raise ValidationAppError(
            "Algunos roles no existen.", {"role_ids": missing}, code="invalid_reference"
        )
    current = await repository.role_ids_of(session, user.id)
    new = [i for i in requested if i not in current]
    for role_id in new:
        session.add(UserRole(user_id=user.id, role_id=role_id))
    await session.flush()
    if new:
        await _audit_roles(session, actor, user.id, current, [*current, *new])
    await session.commit()
    return await _detail(session, user)


async def remove_role(
    session: AsyncSession, user_id: UUID, role_id: UUID, actor: Actor
) -> UserDetail:
    user = await get_or_404(session, User, user_id, _USER)
    current = await repository.role_ids_of(session, user.id)
    if not await repository.remove_role(session, user.id, role_id):
        raise not_found("un rol asignado a este usuario", role_id)
    await _audit_roles(
        session, actor, user.id, current, [r for r in current if r != role_id]
    )
    await session.commit()
    return await _detail(session, user)


async def _audit_roles(
    session: AsyncSession,
    actor: Actor,
    user_id: UUID,
    before: list[UUID],
    after: list[UUID],
) -> None:
    await audit.record_event(
        session,
        actor.entry(
            "leo.users.assign-roles",
            entity_type="user",
            entity_id=str(user_id),
            changes=diff(
                {"role_ids": sorted(str(r) for r in before)},
                {"role_ids": sorted(str(r) for r in after)},
            ),
        ),
    )


# --- aprovisionamiento de pacientes por una app con credencial de servicio ---

PATIENT_APP_SLUG = "acuarius"
PATIENT_ROLE_SLUG = "paciente"
PROVISION_TAG = "leo.users.provision-patient"

_provision_limiter: SlidingWindowLimiter | None = None


def provision_limiter() -> SlidingWindowLimiter:
    """Altas de pacientes por minuto y por app llamadora (en memoria)."""
    global _provision_limiter
    if _provision_limiter is None:
        _provision_limiter = SlidingWindowLimiter(
            get_settings().leo_provision_rate_limit_per_minute, 60
        )
    return _provision_limiter


class PatientConflictError(ConflictError):
    """409 neutro: no revela si choco el usuario, el email o el documento."""

    code = "conflict"

    def __init__(self) -> None:
        super().__init__("No se pudo crear el usuario con los datos indicados.")


class PatientRoleUnavailableError(AppError):
    status_code = 503
    code = "patient_role_unavailable"

    def __init__(self) -> None:
        super().__init__(
            "El rol de paciente no está disponible. Intenta de nuevo más tarde."
        )


async def provision_patient(
    session: AsyncSession,
    data: PatientProvision,
    principal: ServicePrincipal,
    actor: Actor,
) -> PatientRead:
    """Crea un usuario activo con el rol `acuarius/paciente` para una app de
    servicio autorizada. Contrasena debil: 422 (hay que corregirla). Usuario,
    email o documento repetidos: 409 generico, sin decir cual; el detalle
    queda en la auditoria. Siempre calcula el hash argon2 para que el tiempo
    no delate si choco. Audita con actor = servicio."""
    limiter = provision_limiter()
    key = str(principal.application_id)
    wait = limiter.retry_after(key)
    if wait:
        raise TooManyRequestsError(
            "Demasiadas solicitudes de alta. Intenta de nuevo más tarde.", wait
        )
    limiter.hit(key)

    _check_password(data.password, data.username, data.email)
    password_hash = hash_password(data.password)
    role = await roles.active_role_brief(session, PATIENT_APP_SLUG, PATIENT_ROLE_SLUG)
    if role is None:
        raise PatientRoleUnavailableError

    taken = [
        field
        for field, is_taken in (
            ("username", await repository.username_taken(session, data.username)),
            ("email", await repository.email_taken(session, data.email)),
            (
                "document",
                await repository.document_taken(
                    session, data.document_type, data.document_number
                ),
            ),
        )
        if is_taken
    ]
    user = User(**data.model_dump(exclude={"password"}), password_hash=password_hash)
    if not taken:
        try:
            async with session.begin_nested():
                session.add(user)
                await session.flush()
                session.add(UserRole(user_id=user.id, role_id=role.id))
                await session.flush()
        except IntegrityError:  # carrera con otra alta: mismo resultado
            taken = ["race"]
    if taken:
        await audit.record_and_commit(
            session,
            actor.entry(
                PROVISION_TAG,
                result="denied",
                entity_type="user",
                reason="Alta de paciente rechazada por datos repetidos "
                f"({', '.join(taken)}).",
            ),
        )
        raise PatientConflictError
    await session.refresh(user)
    await audit.record_event(
        session,
        actor.entry(
            PROVISION_TAG,
            entity_type="user",
            entity_id=str(user.id),
            changes=diff(
                None, snapshot(user, USER_FIELDS) | {"role": f"acuarius/{role.slug}"}
            ),
            reason=f"Paciente creado por la aplicación «{principal.client_id}».",
        ),
    )
    await session.commit()
    return PatientRead.model_validate(user)
