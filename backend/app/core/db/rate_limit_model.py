"""Tabla `rate_limit_hits`: aciertos del limitador compartido entre procesos
(`LEO_RATE_LIMIT_BACKEND=postgres`, ver `app.core.rate_limit`).

Una fila por intento dentro de la ventana; las vencidas se borran al
consultar. No se referencia desde otras tablas ni lleva `Timestamps`: es un
contador efimero.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class RateLimitHit(Base):
    __tablename__ = "rate_limit_hits"
    __table_args__ = (
        Index("ix_rate_limit_hits_bucket_key_hit_at", "bucket", "key", "hit_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # Limitador (p. ej. `login.ip`) y clave dentro de el (ip, usuario, app).
    bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    hit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
