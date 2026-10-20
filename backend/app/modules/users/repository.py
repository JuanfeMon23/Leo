"""Consultas del modulo `users`."""

from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import only_active, search
from app.modules.users.models import DocumentType, User, UserRole


def list_statement(q: str | None, active: bool | None) -> Select:
    stmt = select(User)
    stmt = search(
        stmt,
        q,
        User.username,
        User.email,
        User.first_name,
        User.last_name,
        User.document_number,
    )
    return only_active(stmt, active, User.is_active)


async def find_by_login(session: AsyncSession, login: str) -> User | None:
    """Usuario por username o email (sin distinguir mayusculas). El username
    no admite `@`, asi que nunca es ambiguo."""
    value = login.strip().lower()
    column = func.lower(User.email) if "@" in value else User.username
    return await session.scalar(select(User).where(column == value))


async def username_taken(session: AsyncSession, username: str) -> bool:
    return (
        await session.scalar(select(User.id).where(User.username == username))
        is not None
    )


async def email_taken(
    session: AsyncSession, email: str, exclude_id: UUID | None = None
) -> bool:
    stmt = select(User.id).where(func.lower(User.email) == email.lower())
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return await session.scalar(stmt) is not None


async def document_taken(
    session: AsyncSession,
    document_type: DocumentType,
    number: str,
    exclude_id: UUID | None = None,
) -> bool:
    stmt = select(User.id).where(
        User.document_type == document_type, User.document_number == number
    )
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return await session.scalar(stmt) is not None


async def role_ids_of(session: AsyncSession, user_id: UUID) -> list[UUID]:
    rows = await session.scalars(
        select(UserRole.role_id).where(UserRole.user_id == user_id)
    )
    return list(rows)


async def remove_role(session: AsyncSession, user_id: UUID, role_id: UUID) -> bool:
    result = await session.execute(
        delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
    )
    return result.rowcount > 0
