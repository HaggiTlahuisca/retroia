"""Capa de persistencia SQLite."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from config import DB_PATH, EXPORTS_DIR
from models import Actividad, Criterio, EjemploRetroalimentacion, Nivel, Recurso, Retroalimentacion, Rubrica
from utils import now_slug


class DatabaseManager:
    """Administra conexión, migraciones y operaciones CRUD."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            self._create_tables(conn)
            self._add_missing_columns(conn)
            self._migrate_legacy(conn)
            conn.commit()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rubricas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                contenido TEXT NOT NULL DEFAULT '',
                criterios_json TEXT,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS actividades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                descripcion TEXT DEFAULT '',
                instrucciones TEXT DEFAULT '',
                rubrica_id INTEGER,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rubrica_id) REFERENCES rubricas(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS recursos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actividad_id INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                tipo TEXT DEFAULT 'Enlace',
                url TEXT DEFAULT '',
                descripcion TEXT DEFAULT '',
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (actividad_id) REFERENCES actividades(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS ejemplos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                contenido TEXT NOT NULL,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS directrices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL DEFAULT 'default',
                contenido TEXT NOT NULL DEFAULT '',
                activo INTEGER DEFAULT 1,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actividad_id INTEGER,
                estudiante TEXT NOT NULL,
                calificacion REAL,
                criterios TEXT,
                observaciones TEXT,
                retroalimentacion TEXT NOT NULL,
                prompt TEXT,
                modelo TEXT,
                temperatura REAL,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (actividad_id) REFERENCES actividades(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    def _add_missing_columns(self, conn: sqlite3.Connection) -> None:
        self._ensure_columns(conn, "actividades", {"instrucciones": "TEXT DEFAULT ''", "fecha_actualizacion": "TEXT"})
        self._ensure_columns(conn, "historial", {"prompt": "TEXT", "temperatura": "REAL"})

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def _migrate_legacy(self, conn: sqlite3.Connection) -> None:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "instrucciones" in tables:
            conn.execute(
                """INSERT OR IGNORE INTO directrices(nombre, contenido)
                   SELECT nombre, contenido FROM instrucciones"""
            )
        if "recursos_actividad" in tables:
            conn.execute(
                """INSERT OR IGNORE INTO recursos(id, actividad_id, titulo, url, tipo, descripcion, fecha_creacion)
                   SELECT id, actividad_id, titulo, url, COALESCE(tipo,'Enlace'), COALESCE(descripcion,''), fecha_agregado
                   FROM recursos_actividad"""
            )
        if "ejemplos_retroalimentacion" in tables:
            conn.execute(
                """INSERT OR IGNORE INTO ejemplos(id, nombre, contenido, fecha_creacion)
                   SELECT id, nombre, contenido, fecha_creacion FROM ejemplos_retroalimentacion"""
            )
        if "retroalimentaciones" in tables:
            conn.execute(
                """INSERT OR IGNORE INTO historial(
                       id, actividad_id, estudiante, calificacion, criterios, observaciones,
                       retroalimentacion, modelo, temperatura, fecha)
                   SELECT id, actividad_id, estudiante_nombre, calificacion, criterios_cumplidos,
                          observaciones, retroalimentacion_texto, modelo_usado, temperatura, fecha_creacion
                   FROM retroalimentaciones"""
            )

    def create_activity(self, item: Actividad, rubrica_id: int | None = None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO actividades(nombre, descripcion, instrucciones, rubrica_id)
                   VALUES (?, ?, ?, ?)""",
                (item.nombre, item.descripcion, item.instrucciones, rubrica_id),
            )
            return int(cur.lastrowid)

    def update_activity(self, item_id: int, item: Actividad, rubrica_id: int | None = None) -> None:
        self._execute(
            """UPDATE actividades SET nombre=?, descripcion=?, instrucciones=?, rubrica_id=?,
               fecha_actualizacion=CURRENT_TIMESTAMP WHERE id=?""",
            (item.nombre, item.descripcion, item.instrucciones, rubrica_id, item_id),
        )

    def delete_activity(self, item_id: int) -> None:
        self._execute("DELETE FROM actividades WHERE id=?", (item_id,))

    def duplicate_activity(self, item_id: int) -> int:
        item = self.get_activity(item_id)
        if not item:
            raise ValueError("Actividad no encontrada")
        item.nombre = f"{item.nombre} (copia)"
        new_id = self.create_activity(item, item.rubrica.id if item.rubrica else None)
        for recurso in self.list_resources(item_id):
            recurso.actividad_id = new_id
            self.create_resource(recurso)
        return new_id

    def list_activities(self, query: str = "") -> list[sqlite3.Row]:
        sql = """SELECT a.*, r.nombre AS rubrica_nombre FROM actividades a
                 LEFT JOIN rubricas r ON r.id=a.rubrica_id"""
        params: tuple[Any, ...] = ()
        if query:
            sql += " WHERE a.nombre LIKE ? OR a.descripcion LIKE ?"
            params = (f"%{query}%", f"%{query}%")
        return self._fetchall(sql + " ORDER BY a.nombre", params)

    def get_activity(self, item_id: int) -> Actividad | None:
        row = self._fetchone("SELECT * FROM actividades WHERE id=?", (item_id,))
        if not row:
            return None
        rubrica = self.get_rubric(row["rubrica_id"]) if row["rubrica_id"] else None
        recursos = self.list_resources(item_id)
        return Actividad(row["id"], row["nombre"], row["descripcion"] or "", row["instrucciones"] or "", rubrica, recursos)

    def create_rubric(self, item: Rubrica) -> int:
        criterios_json = self._rubric_json(item)
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO rubricas(nombre, contenido, criterios_json) VALUES (?, ?, ?)",
                (item.nombre, item.contenido, criterios_json),
            )
            return int(cur.lastrowid)

    def update_rubric(self, item_id: int, item: Rubrica) -> None:
        self._execute(
            """UPDATE rubricas SET nombre=?, contenido=?, criterios_json=?,
               fecha_actualizacion=CURRENT_TIMESTAMP WHERE id=?""",
            (item.nombre, item.contenido, self._rubric_json(item), item_id),
        )

    def delete_rubric(self, item_id: int) -> None:
        self._execute("DELETE FROM rubricas WHERE id=?", (item_id,))

    def duplicate_rubric(self, item_id: int) -> int:
        item = self.get_rubric(item_id)
        if not item:
            raise ValueError("Rúbrica no encontrada")
        item.nombre = f"{item.nombre} (copia)"
        return self.create_rubric(item)

    def list_rubrics(self, query: str = "") -> list[sqlite3.Row]:
        sql, params = "SELECT * FROM rubricas", ()
        if query:
            sql += " WHERE nombre LIKE ? OR contenido LIKE ?"
            params = (f"%{query}%", f"%{query}%")
        return self._fetchall(sql + " ORDER BY nombre", params)

    def get_rubric(self, item_id: int) -> Rubrica | None:
        row = self._fetchone("SELECT * FROM rubricas WHERE id=?", (item_id,))
        if not row:
            return None
        return Rubrica(row["id"], row["nombre"], row["contenido"] or "", self._criteria_from_json(row["criterios_json"]))

    def create_resource(self, item: Recurso) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO recursos(actividad_id,titulo,tipo,url,descripcion) VALUES(?,?,?,?,?)""",
                (item.actividad_id, item.titulo, item.tipo, item.url, item.descripcion),
            )
            return int(cur.lastrowid)

    def update_resource(self, item_id: int, item: Recurso) -> None:
        self._execute(
            """UPDATE recursos SET titulo=?, tipo=?, url=?, descripcion=?,
               fecha_actualizacion=CURRENT_TIMESTAMP WHERE id=?""",
            (item.titulo, item.tipo, item.url, item.descripcion, item_id),
        )

    def delete_resource(self, item_id: int) -> None:
        self._execute("DELETE FROM recursos WHERE id=?", (item_id,))

    def list_resources(self, activity_id: int) -> list[Recurso]:
        rows = self._fetchall("SELECT * FROM recursos WHERE actividad_id=? ORDER BY titulo", (activity_id,))
        return [Recurso(r["titulo"], r["tipo"], r["url"], r["descripcion"], r["id"], r["actividad_id"]) for r in rows]

    def upsert_example(self, item: EjemploRetroalimentacion) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO ejemplos(nombre,contenido) VALUES(?,?)
                   ON CONFLICT(nombre) DO UPDATE SET contenido=excluded.contenido,
                   fecha_actualizacion=CURRENT_TIMESTAMP""",
                (item.nombre, item.contenido),
            )
            return int(cur.lastrowid or 0)

    def delete_example(self, item_id: int) -> None:
        self._execute("DELETE FROM ejemplos WHERE id=?", (item_id,))

    def duplicate_example(self, item_id: int) -> int:
        row = self._fetchone("SELECT * FROM ejemplos WHERE id=?", (item_id,))
        if not row:
            raise ValueError("Ejemplo no encontrado")
        return self.upsert_example(EjemploRetroalimentacion(f"{row['nombre']} (copia)", row["contenido"]))

    def list_examples(self) -> list[sqlite3.Row]:
        return self._fetchall("SELECT * FROM ejemplos ORDER BY nombre")

    def get_directrices(self, name: str = "default") -> str:
        row = self._fetchone("SELECT contenido FROM directrices WHERE nombre=?", (name,))
        return row["contenido"] if row else ""

    def upsert_directrices(self, contenido: str, name: str = "default") -> None:
        self._execute(
            """INSERT INTO directrices(nombre,contenido) VALUES(?,?)
               ON CONFLICT(nombre) DO UPDATE SET contenido=excluded.contenido,
               fecha_actualizacion=CURRENT_TIMESTAMP""",
            (name, contenido),
        )

    def create_history(self, item: Retroalimentacion, activity_id: int | None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO historial(actividad_id,estudiante,calificacion,criterios,observaciones,
                   retroalimentacion,prompt,modelo,temperatura) VALUES(?,?,?,?,?,?,?,?,?)""",
                (activity_id, item.estudiante, item.calificacion, json.dumps(item.criterios, ensure_ascii=False),
                 item.observaciones, item.texto, item.prompt, item.modelo, item.temperatura),
            )
            return int(cur.lastrowid)

    def list_history(self, query: str = "", activity_id: int | None = None) -> list[sqlite3.Row]:
        sql = """SELECT h.*, a.nombre AS actividad FROM historial h
                 LEFT JOIN actividades a ON a.id=h.actividad_id WHERE 1=1"""
        params: list[Any] = []
        if query:
            sql += " AND (h.estudiante LIKE ? OR h.retroalimentacion LIKE ?)"
            params.extend([f"%{query}%", f"%{query}%"])
        if activity_id:
            sql += " AND h.actividad_id=?"
            params.append(activity_id)
        return self._fetchall(sql + " ORDER BY h.fecha DESC", tuple(params))

    def get_history(self, item_id: int) -> sqlite3.Row | None:
        return self._fetchone("SELECT * FROM historial WHERE id=?", (item_id,))

    def delete_history(self, item_id: int) -> None:
        self._execute("DELETE FROM historial WHERE id=?", (item_id,))

    def backup(self) -> Path:
        EXPORTS_DIR.mkdir(exist_ok=True)
        target = EXPORTS_DIR / f"retroalimentaciones_backup_{now_slug()}.db"
        shutil.copy2(self.db_path, target)
        return target

    def export_all_json(self) -> dict[str, list[dict[str, Any]]]:
        tables = ["actividades", "rubricas", "recursos", "ejemplos", "directrices", "historial"]
        return {table: [dict(row) for row in self._fetchall(f"SELECT * FROM {table}")] for table in tables}

    def import_json(self, data: dict[str, Iterable[dict[str, Any]]]) -> None:
        allowed = {"actividades", "rubricas", "recursos", "ejemplos", "directrices", "historial"}
        with self.connect() as conn:
            for table, rows in data.items():
                if table not in allowed:
                    continue
                for row in rows:
                    cols = ",".join(row.keys())
                    marks = ",".join("?" for _ in row)
                    conn.execute(f"INSERT OR REPLACE INTO {table}({cols}) VALUES({marks})", tuple(row.values()))

    @staticmethod
    def _rubric_json(item: Rubrica) -> str | None:
        if not item.criterios:
            return None
        data = {c.nombre: {n.nombre: n.descripcion for n in c.niveles} for c in item.criterios}
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _criteria_from_json(value: str | None) -> list[Criterio]:
        if not value:
            return []
        try:
            data = json.loads(value)
            return [Criterio(k, [Nivel(n, d) for n, d in v.items()]) for k, v in data.items()]
        except json.JSONDecodeError:
            return []

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connect() as conn:
            conn.execute(sql, params)

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute(sql, params))
