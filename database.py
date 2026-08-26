"""Gestor de base de datos compatible con SQLite local y Turso (LibSQL Hrana)."""

from __future__ import annotations

import os
import sqlite3
import json
import random
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

from config import DB_PATH, EXPORTS_DIR
from models import Actividad, Criterio, Frase, Nivel, Recurso, Retroalimentacion, Rubrica
from utils import now_slug

try:
    import libsql
    HAS_LIBSQL = True
except ImportError:
    HAS_LIBSQL = False


class CustomRow(dict):
    """Fila personalizada que permite acceso por clave o por atributo."""
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"Fila no tiene la columna '{name}'")


class LibSQLCursorWrapper:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> LibSQLCursorWrapper:
        self._cursor.execute(sql, params)
        return self

    def fetchone(self) -> Optional[CustomRow]:
        row = self._cursor.fetchone()
        if row is None:
            return None
        if hasattr(self._cursor, "description") and self._cursor.description:
            cols = [col[0] for col in self._cursor.description]
            return CustomRow(zip(cols, row))
        return row

    def fetchall(self) -> list[CustomRow]:
        rows = self._cursor.fetchall()
        if not rows:
            return []
        if hasattr(self._cursor, "description") and self._cursor.description:
            cols = [col[0] for col in self._cursor.description]
            return [CustomRow(zip(cols, r)) for r in rows]
        return rows

    @property
    def lastrowid(self) -> Any:
        return getattr(self._cursor, "lastrowid", None)


class LibSQLConnectionWrapper:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def cursor(self) -> LibSQLCursorWrapper:
        return LibSQLCursorWrapper(self._conn.cursor())

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> LibSQLCursorWrapper:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self) -> None:
        if hasattr(self._conn, "commit"):
            try:
                self._conn.commit()
            except Exception:
                pass

    def rollback(self) -> None:
        if hasattr(self._conn, "rollback"):
            try:
                self._conn.rollback()
            except Exception:
                pass

    def close(self) -> None:
        if hasattr(self._conn, "close"):
            try:
                self._conn.close()
            except Exception:
                pass

    def __enter__(self) -> LibSQLConnectionWrapper:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()


class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.turso_url = os.getenv("TURSO_DATABASE_URL", "").strip()
        self.turso_token = os.getenv("TURSO_AUTH_TOKEN", "").strip()

    def connect(self) -> Any:
        if HAS_LIBSQL and self.turso_url and self.turso_token:
            conn = libsql.connect(self.turso_url, auth_token=self.turso_token)
            return LibSQLConnectionWrapper(conn)
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_tables()
        self._add_missing_columns()
        self._init_default_directrices()

    def _create_tables(self) -> None:
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS actividades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    proposito TEXT NOT NULL,
                    instrucciones TEXT NOT NULL,
                    grupo TEXT DEFAULT 'M11C1G77-050',
                    orden INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS criterios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actividad_id INTEGER NOT NULL,
                    nombre TEXT NOT NULL,
                    orden INTEGER DEFAULT 0,
                    FOREIGN KEY(actividad_id) REFERENCES actividades(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS niveles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    criterio_id INTEGER NOT NULL,
                    nombre TEXT NOT NULL,
                    puntaje REAL NOT NULL,
                    descripcion TEXT NOT NULL,
                    FOREIGN KEY(criterio_id) REFERENCES criterios(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recursos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actividad_id INTEGER,
                    tipo TEXT NOT NULL,
                    titulo TEXT NOT NULL,
                    url TEXT NOT NULL,
                    descripcion TEXT NOT NULL,
                    FOREIGN KEY(actividad_id) REFERENCES actividades(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS directrices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE NOT NULL,
                    contenido TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS frases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    texto TEXT NOT NULL,
                    autor TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS historial (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actividad_id INTEGER,
                    estudiante TEXT NOT NULL,
                    actividad_nombre TEXT NOT NULL,
                    fecha TEXT NOT NULL,
                    calificacion REAL NOT NULL,
                    modelo_usado TEXT NOT NULL,
                    retroalimentacion TEXT NOT NULL,
                    criterios_evaluados TEXT,
                    observaciones TEXT,
                    prompt_usado TEXT,
                    temperatura REAL,
                    FOREIGN KEY(actividad_id) REFERENCES actividades(id) ON DELETE SET NULL
                )
            """)

    def _add_missing_columns(self) -> None:
        with self.connect() as conn:
            try:
                conn.execute("ALTER TABLE actividades ADD COLUMN grupo TEXT DEFAULT 'M11C1G77-050'")
            except Exception:
                pass

    def _init_default_directrices(self) -> None:
        defaults = {
            "saludo": "Inicia con 'Apreciable, [Nombre]'. Resalta fortalezas de forma personalizada evitando muletillas.",
            "criterios": "Menciona los criterios en orden numérico estricto indicando el nivel obtenido en minúsculas y negritas.",
            "areas_oportunidad": "Redacta áreas de oportunidad en prosa fluida y natural sin subtítulos Markdown.",
            "recursos": "Si existen recursos registrados, compártelos en párrafos independientes.",
            "cierre": "Para finalizar con tu retroalimentación nuevamente te felicito y agradezco el que hayas entregado tu actividad. Me despido con una frase motivadora.",
            "firma": "Haggi de Jesús Tlahuisca Hernández\nAsesor virtual\n21D28277\n[Grupo]"
        }
        for name, content in defaults.items():
            try:
                with self.connect() as conn:
                    conn.execute("INSERT OR IGNORE INTO directrices(nombre, contenido) VALUES (?, ?)", (name, content))
            except Exception:
                pass

    # ==========================================
    # GESTIÓN DE ACTIVIDADES
    # ==========================================
    def list_activities(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM actividades ORDER BY orden ASC, id ASC")
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_activity(self, actividad_id: int) -> Optional[Actividad]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM actividades WHERE id = ?", (actividad_id,))
            row = cur.fetchone()
            if not row:
                return None
            
            grupo = row["grupo"] if "grupo" in row and row["grupo"] else "M11C1G77-050"
            act = Actividad(row["nombre"], row["proposito"], row["instrucciones"], grupo, row["id"], row["orden"])
            
            cur_crit = conn.execute("SELECT * FROM criterios WHERE actividad_id = ? ORDER BY orden ASC, id ASC", (actividad_id,))
            for crit_row in cur_crit.fetchall():
                criterio = Criterio(crit_row["nombre"], crit_row["id"], crit_row["orden"])
                cur_niv = conn.execute("SELECT * FROM niveles WHERE criterio_id = ? ORDER BY puntaje DESC", (crit_row["id"],))
                for niv_row in cur_niv.fetchall():
                    criterio.add_nivel(Nivel(niv_row["nombre"], float(niv_row["puntaje"]), niv_row["descripcion"], niv_row["id"]))
                act.rubrica.add_criterio(criterio)

            cur_rec = conn.execute("SELECT * FROM recursos WHERE actividad_id = ? OR actividad_id IS NULL", (actividad_id,))
            for rec_row in cur_rec.fetchall():
                act.add_recurso(Recurso(rec_row["tipo"], rec_row["titulo"], rec_row["url"], rec_row["descripcion"], rec_row["id"]))

            return act

    def create_activity(self, actividad: Actividad) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO actividades (nombre, proposito, instrucciones, grupo, orden) VALUES (?, ?, ?, ?, ?)",
                (actividad.nombre, actividad.proposito, actividad.instrucciones, actividad.grupo, actividad.orden)
            )
            return cur.lastrowid or 0

    def update_activity(self, actividad: Actividad) -> None:
        if actividad.id is None:
            return
        with self.connect() as conn:
            conn.execute(
                "UPDATE actividades SET nombre = ?, proposito = ?, instrucciones = ?, grupo = ?, orden = ? WHERE id = ?",
                (actividad.nombre, actividad.proposito, actividad.instrucciones, actividad.grupo, actividad.orden, actividad.id)
            )

    def delete_activity(self, actividad_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM actividades WHERE id = ?", (actividad_id,))

    # ==========================================
    # GESTIÓN DE CRITERIOS Y NIVELES (RÚBRICA)
    # ==========================================
    def add_criterio(self, actividad_id: int, criterio: Criterio) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO criterios (actividad_id, nombre, orden) VALUES (?, ?, ?)",
                (actividad_id, criterio.nombre, criterio.orden)
            )
            return cur.lastrowid or 0

    def delete_criterio(self, criterio_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM criterios WHERE id = ?", (criterio_id,))

    def add_nivel(self, criterio_id: int, nivel: Nivel) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO niveles (criterio_id, nombre, puntaje, descripcion) VALUES (?, ?, ?, ?)",
                (criterio_id, nivel.nombre, nivel.puntaje, nivel.descripcion)
            )
            return cur.lastrowid or 0

    def delete_nivel(self, nivel_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM niveles WHERE id = ?", (nivel_id,))

    # ==========================================
    # GESTIÓN DE RECURSOS
    # ==========================================
    def get_recursos_by_actividad(self, actividad_id: int) -> list[Recurso]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM recursos WHERE actividad_id = ? ORDER BY id DESC", (actividad_id,))
            return [Recurso(r["tipo"], r["titulo"], r["url"], r["descripcion"], r["id"]) for r in cur.fetchall()]

    def get_recursos_globales(self) -> list[Recurso]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM recursos WHERE actividad_id IS NULL ORDER BY id DESC")
            return [Recurso(r["tipo"], r["titulo"], r["url"], r["descripcion"], r["id"]) for r in cur.fetchall()]

    def add_recurso(self, actividad_id: Optional[int], recurso: Recurso) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO recursos (actividad_id, tipo, titulo, url, descripcion) VALUES (?, ?, ?, ?, ?)",
                (actividad_id, recurso.tipo, recurso.titulo, recurso.url, recurso.descripcion)
            )
            return cur.lastrowid or 0

    def add_recurso_global(self, recurso: Recurso) -> int:
        return self.add_recurso(None, recurso)

    def delete_recurso(self, recurso_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM recursos WHERE id = ?", (recurso_id,))

    # ==========================================
    # DIRECTRICES PEDAGÓGICAS
    # ==========================================
    def get_all_directrices(self) -> dict[str, str]:
        with self.connect() as conn:
            cur = conn.execute("SELECT nombre, contenido FROM directrices")
            return {r["nombre"]: r["contenido"] for r in cur.fetchall()}

    def get_directriz(self, nombre: str) -> str:
        with self.connect() as conn:
            cur = conn.execute("SELECT contenido FROM directrices WHERE nombre = ?", (nombre,))
            row = cur.fetchone()
            return row["contenido"] if row else ""

    def update_directriz(self, nombre: str, contenido: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO directrices (nombre, contenido) VALUES (?, ?) ON CONFLICT(nombre) DO UPDATE SET contenido = excluded.contenido",
                (nombre, contenido)
            )

    # ==========================================
    # FRASES MOTIVACIONALES
    # ==========================================
    def get_frases(self) -> list[Frase]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM frases ORDER BY id DESC")
            return [Frase(r["texto"], r["autor"], r["id"]) for r in cur.fetchall()]

    def get_random_frase(self) -> Optional[Frase]:
        frases = self.get_frases()
        return random.choice(frases) if frases else None

    def add_frase(self, frase: Frase) -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO frases (texto, autor) VALUES (?, ?)", (frase.texto, frase.autor))
            return cur.lastrowid or 0

    def delete_frase(self, frase_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM frases WHERE id = ?", (frase_id,))

    # ==========================================
    # HISTORIAL DE EVALUACIONES
    # ==========================================
    def create_history(self, item: Retroalimentacion, actividad_id: Optional[int] = None) -> int:
        with self.connect() as conn:
            crit_json = json.dumps(item.criterios_evaluados, ensure_ascii=False)
            fecha_str = item.fecha if isinstance(item.fecha, str) else item.fecha.strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute("""
                INSERT INTO historial (
                    actividad_id, estudiante, actividad_nombre, fecha, calificacion,
                    modelo_usado, retroalimentacion, criterios_evaluados, observaciones,
                    prompt_usado, temperatura
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                actividad_id, item.estudiante, item.actividad_nombre, fecha_str,
                item.calificacion, item.modelo_usado, item.texto_generado, crit_json,
                item.observaciones, item.prompt_usado, item.temperatura
            ))
            return cur.lastrowid or 0

    def list_history(
        self,
        limit: int = 100,
        actividad_id: Optional[int] = None,
        estudiante: str = "",
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

    def get_history(self, history_id: int) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute("SELECT * FROM historial WHERE id = ?", (history_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def delete_history(self, history_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM historial WHERE id = ?", (history_id,))

    def clear_history(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM historial")

    # ==========================================
    # IMPORTACIÓN DE RÚBRICAS JSON
    # ==========================================
    def import_rubrica_json(self, actividad_id: int, json_data: str | dict) -> None:
        data = json.loads(json_data) if isinstance(json_data, str) else json_data
        with self.connect() as conn:
            criterios = data.get("criterios", [])
            for ord_c, crit_data in enumerate(criterios, start=1):
                cur = conn.execute(
                    "INSERT INTO criterios (actividad_id, nombre, orden) VALUES (?, ?, ?)",
                    (actividad_id, crit_data["nombre"], ord_c)
                )
                criterio_id = cur.lastrowid
                for niv_data in crit_data.get("niveles", []):
                    conn.execute(
                        "INSERT INTO niveles (criterio_id, nombre, puntaje, descripcion) VALUES (?, ?, ?, ?)",
                        (criterio_id, niv_data["nombre"], float(niv_data["puntaje"]), niv_data.get("descripcion", ""))
                    )
