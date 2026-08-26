"""Capa de persistencia SQLite y libSQL (Turso)."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

from config import DB_PATH, EXPORTS_DIR
from models import Actividad, Criterio, Frase, Nivel, Recurso, Retroalimentacion, Rubrica
from utils import now_slug


class CustomRow:
    def __init__(self, cursor: Any, row_tuple: tuple[Any, ...]) -> None:
        columns = [col[0] for col in cursor.description]
        self._data = dict(zip(columns, row_tuple))
        self._tuple = row_tuple

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return self._tuple[key]
        return self._data[key]

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def items(self) -> Any:
        return self._data.items()

    def __iter__(self) -> Any:
        return iter(self._tuple)

    def __len__(self) -> int:
        return len(self._tuple)


class LibSQLCursorWrapper:
    def __init__(self, cursor: Any, conn_wrapper: LibSQLConnectionWrapper) -> None:
        self._cursor = cursor
        self._conn_wrapper = conn_wrapper

    @property
    def description(self) -> Any:
        return self._cursor.description

    @property
    def lastrowid(self) -> Any:
        return self._cursor.lastrowid

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> LibSQLCursorWrapper:
        self._cursor.execute(sql, params)
        return self

    def fetchone(self) -> Any:
        row = self._cursor.fetchone()
        if row is not None and self._conn_wrapper.row_factory:
            return self._conn_wrapper.row_factory(self, row)
        return row

    def fetchall(self) -> list[Any]:
        rows = self._cursor.fetchall()
        if self._conn_wrapper.row_factory:
            return [self._conn_wrapper.row_factory(self, r) for r in rows]
        return list(rows)

    def __iter__(self) -> Any:
        rows = self._cursor.fetchall()
        if self._conn_wrapper.row_factory:
            for r in rows:
                yield self._conn_wrapper.row_factory(self, r)
        else:
            yield from rows


class LibSQLConnectionWrapper:
    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self.row_factory = None

    def cursor(self) -> LibSQLCursorWrapper:
        return LibSQLCursorWrapper(self._conn.cursor(), self)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> LibSQLCursorWrapper:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self) -> None:
        if hasattr(self._conn, "commit"):
            self._conn.commit()

    def rollback(self) -> None:
        if hasattr(self._conn, "rollback"):
            self._conn.rollback()

    def close(self) -> None:
        if hasattr(self._conn, "close"):
            self._conn.close()

    def __enter__(self) -> LibSQLConnectionWrapper:
        if hasattr(self._conn, "__enter__"):
            self._conn.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        if hasattr(self._conn, "__exit__"):
            return self._conn.__exit__(exc_type, exc_val, exc_tb)
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        return False


class DatabaseManager:
    """Administra conexión, migraciones y operaciones CRUD."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            self._create_tables(conn)
            self._add_missing_columns(conn)
            self._init_default_directrices(conn)
            conn.commit()

    def connect(self) -> Any:
        import os
        url = os.getenv("TURSO_DATABASE_URL")
        token = os.getenv("TURSO_AUTH_TOKEN")
        
        if url and token:
            import libsql
            native_conn = libsql.connect(database=url, auth_token=token)
            conn = LibSQLConnectionWrapper(native_conn)
        else:
            conn = sqlite3.connect(self.db_path)
            
        conn.row_factory = lambda cursor, row_tuple: CustomRow(cursor, row_tuple)
        
        try:
            conn.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
        return conn

    def _create_tables(self, conn: Any) -> None:
        script = """
            CREATE TABLE IF NOT EXISTS rubricas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                contenido TEXT NOT NULL DEFAULT '',
                criterios_json TEXT,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS banco_frases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                texto TEXT NOT NULL,
                autor TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS banco_recursos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                tipo TEXT DEFAULT 'Enlace',
                url TEXT DEFAULT '',
                descripcion TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS actividades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                descripcion TEXT DEFAULT '',
                instrucciones TEXT DEFAULT '',
                rubrica_id INTEGER,
                frase_id INTEGER,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rubrica_id) REFERENCES rubricas(id) ON DELETE SET NULL,
                FOREIGN KEY (frase_id) REFERENCES banco_frases(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS rel_actividad_recurso (
                actividad_id INTEGER,
                recurso_id INTEGER,
                PRIMARY KEY (actividad_id, recurso_id),
                FOREIGN KEY (actividad_id) REFERENCES actividades(id) ON DELETE CASCADE,
                FOREIGN KEY (recurso_id) REFERENCES banco_recursos(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS directrices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
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
            """
        for statement in script.split(";"):
            if statement.strip():
                conn.execute(statement)

    def _add_missing_columns(self) -> None:
        with self.connect() as conn:
            try:
                conn.execute("ALTER TABLE actividades ADD COLUMN grupo TEXT DEFAULT 'M11C1G77-050'")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE actividades ADD COLUMN orden INTEGER DEFAULT 0")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE actividades ADD COLUMN proposito TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE actividades ADD COLUMN instrucciones TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE criterios ADD COLUMN orden INTEGER DEFAULT 0")
            except Exception:
                pass

    def _init_default_directrices(self, conn: Any) -> None:
        defaults = {
            "grupo": "M11C1G77-050",
            "saludo": "Coloca un saludo formal y dirígete al estudiante por su nombre.",
            "fortalezas": "Considera los aspectos destacables del producto que el estudiante entregó...",
            "areas_oportunidad": "Describe los aspectos en los que el estudiante requiere mejorar...",
            "sugerencias": "Brinda información suficiente, variada y pertinente...",
            "recursos_apoyo": "Recomienda materiales y recursos de fuentes confiables...",
            "despedida": "Incluye una frase cordial como muestra de atención.",
            "firma": "Coloca tu nombre y cargo para que el estudiante identifique quién envía."
        }
        for name, content in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO directrices(nombre, contenido) VALUES(?, ?)",
                (name, content)
            )

    @staticmethod
    def _ensure_columns(conn: Any, table: str, columns: dict[str, str]) -> None:
        try:
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        except Exception:
            pass

    # --- Frases ---
    def create_frase(self, texto: str, autor: str) -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO banco_frases(texto, autor) VALUES (?, ?)", (texto, autor))
            return int(cur.lastrowid)

    def update_frase(self, id: int, texto: str, autor: str) -> None:
        self._execute("UPDATE banco_frases SET texto=?, autor=? WHERE id=?", (texto, autor, id))

    def list_frases(self) -> list[Frase]:
        rows = self._fetchall("SELECT * FROM banco_frases ORDER BY id DESC")
        return [Frase(r["texto"], r["autor"], r["id"]) for r in rows]
        
    def delete_frase(self, id: int) -> None:
        self._execute("DELETE FROM banco_frases WHERE id=?", (id,))

    # --- Recursos Globales ---
    def create_recurso(self, r: Recurso) -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO banco_recursos(titulo, tipo, url, descripcion) VALUES (?,?,?,?)",
                               (r.titulo, r.tipo, r.url, r.descripcion))
            return int(cur.lastrowid)

    def update_recurso(self, id: int, r: Recurso) -> None:
        self._execute("UPDATE banco_recursos SET titulo=?, tipo=?, url=?, descripcion=? WHERE id=?",
                      (r.titulo, r.tipo, r.url, r.descripcion, id))

    def list_recursos_globales(self) -> list[Recurso]:
        rows = self._fetchall("SELECT * FROM banco_recursos ORDER BY titulo")
        return [Recurso(r["titulo"], r["tipo"], r["url"], r["descripcion"], r["id"]) for r in rows]

    def delete_recurso(self, id: int) -> None:
        self._execute("DELETE FROM banco_recursos WHERE id=?", (id,))
        self._execute("DELETE FROM rel_actividad_recurso WHERE recurso_id=?", (id,))

    # --- Actividades ---
    def create_activity(self, item: Actividad, rubrica_id: int | None, frase_id: int | None, recursos_ids: list[int]) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO actividades(nombre, descripcion, instrucciones, rubrica_id, frase_id) VALUES (?, ?, ?, ?, ?)",
                (item.nombre, item.proposito, item.instrucciones, rubrica_id, frase_id)
            )
            act_id = int(cur.lastrowid)
            for r_id in recursos_ids:
                conn.execute("INSERT INTO rel_actividad_recurso(actividad_id, recurso_id) VALUES (?, ?)", (act_id, r_id))
            return act_id

    def update_activity(self, item_id: int, item: Actividad, rubrica_id: int | None, frase_id: int | None, recursos_ids: list[int]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE actividades SET nombre=?, descripcion=?, instrucciones=?, rubrica_id=?, frase_id=?, fecha_actualizacion=CURRENT_TIMESTAMP WHERE id=?",
                (item.nombre, item.proposito, item.instrucciones, rubrica_id, frase_id, item_id)
            )
            conn.execute("DELETE FROM rel_actividad_recurso WHERE actividad_id=?", (item_id,))
            for r_id in recursos_ids:
                conn.execute("INSERT INTO rel_actividad_recurso(actividad_id, recurso_id) VALUES (?, ?)", (item_id, r_id))

    def delete_activity(self, item_id: int) -> None:
        self._execute("DELETE FROM actividades WHERE id=?", (item_id,))
        self._execute("DELETE FROM rel_actividad_recurso WHERE actividad_id=?", (item_id,))

    def list_activities(self, query: str = "") -> list[Any]:
        sql = "SELECT a.*, r.nombre AS rubrica_nombre FROM actividades a LEFT JOIN rubricas r ON r.id=a.rubrica_id"
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
        
        frase = None
        if row["frase_id"]:
            f_row = self._fetchone("SELECT * FROM banco_frases WHERE id=?", (row["frase_id"],))
            if f_row:
                frase = Frase(f_row["texto"], f_row["autor"], f_row["id"])
                
        rec_rows = self._fetchall(
            "SELECT b.* FROM banco_recursos b JOIN rel_actividad_recurso rel ON b.id = rel.recurso_id WHERE rel.actividad_id=?", 
            (item_id,)
        )
        recursos = [Recurso(r["titulo"], r["tipo"], r["url"], r["descripcion"], r["id"]) for r in rec_rows]
        
        return Actividad(row["id"], row["nombre"], row["descripcion"] or "", row["instrucciones"] or "", rubrica, frase, recursos)

    # --- Rúbricas ---
    def create_rubric(self, item: Rubrica) -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO rubricas(nombre, contenido, criterios_json) VALUES (?, ?, ?)",
                               (item.nombre, item.contenido, self._rubric_json(item)))
            return int(cur.lastrowid)

    def update_rubric(self, item_id: int, item: Rubrica) -> None:
        self._execute(
            "UPDATE rubricas SET nombre=?, contenido=?, criterios_json=?, fecha_actualizacion=CURRENT_TIMESTAMP WHERE id=?",
            (item.nombre, item.contenido, self._rubric_json(item), item_id)
        )

    def delete_rubric(self, item_id: int) -> None:
        self._execute("DELETE FROM rubricas WHERE id=?", (item_id,))

    def list_rubrics(self, query: str = "") -> list[Any]:
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

    # --- Directrices Seccionadas ---
    def get_all_directrices(self) -> dict[str, str]:
        rows = self._fetchall("SELECT nombre, contenido FROM directrices")
        return {r["nombre"]: r["contenido"] for r in rows}

    def update_directriz(self, nombre: str, contenido: str) -> None:
        self._execute("UPDATE directrices SET contenido=?, fecha_actualizacion=CURRENT_TIMESTAMP WHERE nombre=?", (contenido, nombre))

    # --- Historial ---
    def create_history(self, item: Retroalimentacion, activity_id: int | None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO historial(actividad_id,estudiante,calificacion,criterios,observaciones,retroalimentacion,prompt,modelo,temperatura) VALUES(?,?,?,?,?,?,?,?,?)",
                (activity_id, item.estudiante, item.calificacion, json.dumps(item.criterios, ensure_ascii=False),
                 item.observaciones, item.texto, item.prompt, item.modelo, item.temperatura)
            )
            return int(cur.lastrowid)

    def list_history(
        self,
        estudiante: str = "",
        actividad_id: Optional[int] = None,
        limit: int = 500,
        fecha_inicio: Optional[str] = None,
        fecha_fin: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM historial WHERE 1=1"
        params: list[Any] = []

        if actividad_id:
            sql += " AND actividad_id = ?"
            params.append(actividad_id)
        if estudiante:
            sql += " AND estudiante LIKE ?"
            params.append(f"%{estudiante}%")
        if fecha_inicio:
            sql += " AND date(fecha) >= date(?)"
            params.append(fecha_inicio)
        if fecha_fin:
            sql += " AND date(fecha) <= date(?)"
            params.append(fecha_fin)

        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self.connect() as conn:
            cur = conn.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

        
    def backup(self) -> Path:
        EXPORTS_DIR.mkdir(exist_ok=True)
        target = EXPORTS_DIR / f"retroalimentaciones_backup_{now_slug()}.db"
        shutil.copy2(self.db_path, target)
        return target

    def export_all_json(self) -> dict[str, list[dict[str, Any]]]:
        tables = ["actividades", "rubricas", "banco_recursos", "banco_frases", "directrices", "historial"]
        return {table: [dict(row) for row in self._fetchall(f"SELECT * FROM {table}")] for table in tables}

    def import_json(self, data: dict[str, Iterable[dict[str, Any]]]) -> None:
        with self.connect() as conn:
            for table, rows in data.items():
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

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> Any | None:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        with self.connect() as conn:
            return list(conn.execute(sql, params))
