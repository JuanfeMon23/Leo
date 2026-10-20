"""Semillas idempotentes (insert-if-missing por clave de negocio: slug, tag,
username), separadas de las migraciones.

Cada semilla recibe una `Connection` sincronica de SQLAlchemy (desde
`AsyncConnection.run_sync` o el runner `uv run python -m app.core.db.seeds`)
y escribe con `INSERT ... ON CONFLICT DO NOTHING`: nunca pisa lo que el
admin haya editado despues.
"""
