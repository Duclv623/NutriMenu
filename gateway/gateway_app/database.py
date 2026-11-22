from contextlib import contextmanager

import psycopg
from fastapi import HTTPException
from psycopg import sql


class GatewayDatabase:
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def connect(self):
        if not self.settings.postgres_dsn.get_secret_value():
            raise HTTPException(503, "Gateway chưa được cấu hình PostgreSQL.")
        try:
            with psycopg.connect(
                self.settings.postgres_dsn.get_secret_value(), connect_timeout=5
            ) as db:
                db.execute(
                    sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(
                        sql.Identifier(self.settings.postgres_schema)
                    )
                )
                yield db
        except psycopg.Error:
            raise HTTPException(
                503, "Không truy cập được dữ liệu gateway trong PostgreSQL."
            ) from None

    def initialize(self):
        with self.connect() as db:
            db.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(self.settings.postgres_schema)
                )
            )

    def import_legacy(self, db):
        if (
            not self.settings.import_legacy_state
            or self.settings.postgres_schema == self.settings.legacy_schema
        ):
            return
        source = self.settings.legacy_schema
        # Idempotent copy only. Old data stays intact for rollback; never infer
        # ownership from the legacy Node state.json or assign its user 1 plans.
        exists = db.execute(
            "SELECT to_regclass(%s),to_regclass(%s)",
            (source + ".team_identities", source + ".team_ui_state"),
        ).fetchone()
        if all(exists):
            db.execute(
                sql.SQL(
                    "INSERT INTO team_identities(account_id,service_user_id) SELECT account_id,service_user_id FROM {}.team_identities ON CONFLICT(account_id) DO NOTHING"
                ).format(sql.Identifier(source))
            )
            db.execute(
                sql.SQL(
                    "INSERT INTO team_ui_state(account_id,state_key,value) SELECT account_id,state_key,value FROM {}.team_ui_state WHERE state_key <> 'profileMeta' ON CONFLICT(account_id,state_key) DO NOTHING"
                ).format(sql.Identifier(source))
            )
            db.execute(
                "SELECT setval(pg_get_serial_sequence('team_identities','service_user_id'), GREATEST(COALESCE((SELECT MAX(service_user_id) FROM team_identities),1000000000),1000000000), true)"
            )
