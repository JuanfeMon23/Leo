-- Roles de BD de minimo privilegio para Leo (idempotente; ver README, seccion
-- "Roles de BD de minimo privilegio").
--
--   leo_migrator  duenio del esquema y de los objetos; hace el DDL. SOLO lo
--                 usa Alembic (MIGRATION_DATABASE_URL).
--   leo_app       lo que usa la API (DATABASE_URL): SELECT/INSERT/UPDATE/DELETE
--                 sobre las tablas, USAGE en las secuencias. Sin DDL, sin
--                 TRUNCATE, sin acceso a alembic_version; sobre audit_events
--                 y settings_history (append-only) solo SELECT e INSERT;
--                 sobre settings SELECT/INSERT/UPDATE (sin DELETE). Sin superusuario.
--
-- Correr como superusuario (o un rol que pueda crear roles y cambiar duenios),
-- conectado a la BD de Leo:
--
--   psql -d leo -v ON_ERROR_STOP=1 -f deploy/db_roles.sql
--
-- NO define contrasenas (no hay secretos en el repo): los roles se crean
-- LOGIN sin contrasena y no pueden entrar hasta que el operador la fije, p. ej.
-- con `\password leo_app` en psql. Volver a correr despues de CADA migracion que
-- agregue tablas: los permisos no se heredan solos (a proposito: una tabla
-- nueva falla cerrada hasta que se re-aplica el script).

-- 1) Roles (sin superusuario, sin crear BD/roles, sin saltarse RLS).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'leo_migrator') THEN
        CREATE ROLE leo_migrator LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'leo_app') THEN
        CREATE ROLE leo_app LOGIN;
    END IF;
END
$$;

ALTER ROLE leo_migrator NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE leo_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- 2) Conexion a esta BD.
DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO leo_app, leo_migrator', current_database()
    );
END
$$;

-- 3) leo_migrator es duenio del esquema y de sus tablas y funciones.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO leo_migrator;

DO $$
DECLARE
    obj record;
BEGIN
    FOR obj IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tableowner <> 'leo_migrator'
    LOOP
        -- Las secuencias de columnas serial/identity cambian de duenio con la tabla.
        EXECUTE format('ALTER TABLE public.%I OWNER TO leo_migrator', obj.tablename);
    END LOOP;
    FOR obj IN
        SELECT p.oid::regprocedure AS signature
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prokind = 'f'
          AND pg_get_userbyid(p.proowner) <> 'leo_migrator'
          AND NOT EXISTS (
              SELECT 1 FROM pg_depend d
              WHERE d.objid = p.oid AND d.deptype = 'e'
          )
    LOOP
        EXECUTE format('ALTER FUNCTION %s OWNER TO leo_migrator', obj.signature);
    END LOOP;
END
$$;

-- 4) leo_app: solo DML. Se parte de cero para quitar lo que sobrara.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM leo_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM leo_app;
GRANT USAGE ON SCHEMA public TO leo_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO leo_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO leo_app;

-- Excepciones: auditoria append-only (solo leer y agregar) y la tabla de
-- control de Alembic (la API no la necesita).
DO $$
BEGIN
    IF to_regclass('public.audit_events') IS NOT NULL THEN
        REVOKE ALL ON TABLE public.audit_events FROM leo_app;
        GRANT SELECT, INSERT ON TABLE public.audit_events TO leo_app;
    END IF;
    -- Historial de ajustes: append-only (solo leer y agregar).
    IF to_regclass('public.settings_history') IS NOT NULL THEN
        REVOKE ALL ON TABLE public.settings_history FROM leo_app;
        GRANT SELECT, INSERT ON TABLE public.settings_history TO leo_app;
    END IF;
    -- Ajustes vigentes: se editan pero no se borran.
    IF to_regclass('public.settings') IS NOT NULL THEN
        REVOKE ALL ON TABLE public.settings FROM leo_app;
        GRANT SELECT, INSERT, UPDATE ON TABLE public.settings TO leo_app;
    END IF;
    IF to_regclass('public.alembic_version') IS NOT NULL THEN
        REVOKE ALL ON TABLE public.alembic_version FROM leo_app;
    END IF;
END
$$;
