import hashlib
import hmac
import os
import sqlite3
from datetime import date
from pathlib import Path

import streamlit as st


DATABASE_PATH = Path(__file__).with_name("inventario.db")
LOGO_PATH = Path(__file__).with_name("Logo-con-Slogan.jpg")
DEJANDO_HUELLA_LOGO_PATH = Path(__file__).with_name("logo-dejando-huella.png")
COMPANY_LOGOS = {
    "Equipos Gleason S.A.": LOGO_PATH,
    "Dejando Huella Fertilidad": DEJANDO_HUELLA_LOGO_PATH,
}
PASSWORD_ITERATIONS = 310_000

FIELD_GROUPS = {
    "Identificación y asignación": [
        ("proveedor", "Proveedor"),
        ("entrada_factura", "Entrada / factura"),
        ("nombre_equipo", "Nombre del equipo"),
        ("tipo_equipo", "Tipo de equipo"),
        ("area", "Área"),
        ("asignado", "Asignado a"),
        ("cargo", "Cargo"),
        ("sede", "Sede"),
    ],
    "Características del equipo": [
        ("equipo_modelo", "Modelo del equipo"),
        ("marca", "Marca"),
        ("serial", "Serial del equipo"),
        ("disco", "Disco"),
        ("procesador", "Procesador"),
        ("ram_gb", "RAM (GB)"),
        ("tarjeta_grafica", "Tarjeta gráfica"),
        ("monitor_modelo", "Modelo del monitor"),
        ("monitor_serial", "Serial del monitor"),
    ],
    "Software y acceso": [
        ("sistema_operativo", "Sistema operativo"),
        ("licencia_office", "Licencia Office"),
        ("serial_licencia", "Serial de licencia"),
        ("tenant", "Tenant"),
        ("correo_entra_id", "Correo ENTRA ID"),
        ("usuario", "Usuario"),
        ("servidor", "Servidor"),
        ("id_rustdesk", "ID RUSTDESK"),
    ],
    "Compra y mantenimiento": [
        ("fecha_compra", "Fecha de compra"),
        ("garantia", "Garantía"),
        ("observacion", "Observación"),
        ("mantenimiento", "Mantenimiento"),
    ],
}
FIELDS = [field for group in FIELD_GROUPS.values() for field in group]
FIELD_KEYS = [key for key, _ in FIELDS]
INVENTORY_COLUMNS = {
    "nombre_equipo": "Nombre del equipo",
    "tipo_equipo": "Tipo de equipo",
    "marca": "Marca",
    "serial": "Serial",
    "area": "Área",
    "asignado": "Asignado a",
    "sede": "Sede",
    "fecha_compra": "Fecha de compra",
}

st.set_page_config(page_title="Inventario | Equipos Gleason", page_icon="📋", layout="wide")


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    definitions = ", ".join(f'"{key}" TEXT NOT NULL DEFAULT \'\' ' for key in FIELD_KEYS)
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                username TEXT NOT NULL UNIQUE,
                salt BLOB NOT NULL,
                password_hash BLOB NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE
            )
            """
        )
        connection.executemany(
            "INSERT OR IGNORE INTO companies (name) VALUES (?)",
            [
                ("Equipos Gleason S.A.",),
                ("Dejando Huella Fertilidad",),
            ],
        )
        default_company_id = connection.execute(
            "SELECT id FROM companies WHERE name = ?",
            ("Equipos Gleason S.A.",),
        ).fetchone()["id"]
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS equipment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                {definitions},
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        equipment_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(equipment)")
        }
        if "company_id" not in equipment_columns:
            connection.execute(
                "ALTER TABLE equipment ADD COLUMN company_id INTEGER REFERENCES companies(id)"
            )
        connection.execute(
            "UPDATE equipment SET company_id = ? WHERE company_id IS NULL",
            (default_company_id,),
        )


def admin_exists():
    with get_connection() as connection:
        return connection.execute("SELECT 1 FROM admin WHERE id = 1").fetchone() is not None


def create_admin(password):
    salt = os.urandom(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO admin (id, username, salt, password_hash) VALUES (1, ?, ?, ?)",
            ("admin", salt, password_hash),
        )


def authenticate_admin(password):
    with get_connection() as connection:
        admin = connection.execute(
            "SELECT salt, password_hash FROM admin WHERE id = 1 AND username = ?",
            ("admin",),
        ).fetchone()
    if admin is None:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), admin["salt"], PASSWORD_ITERATIONS
    )
    return hmac.compare_digest(candidate, admin["password_hash"])


def get_companies():
    with get_connection() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT id, name FROM companies ORDER BY name COLLATE NOCASE"
            ).fetchall()
        ]


def create_company(name):
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO companies (name) VALUES (?)", (name.strip(),)
        )
        return cursor.lastrowid


def get_equipment(company_id):
    with get_connection() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT id, "
                + ", ".join(f'"{key}"' for key in FIELD_KEYS)
                + " FROM equipment WHERE company_id = ? ORDER BY id DESC",
                (company_id,),
            ).fetchall()
        ]


def save_equipment(values, company_id, equipment_id=None):
    fields_sql = ", ".join(f'"{key}"' for key in FIELD_KEYS)
    values_sql = ", ".join("?" for _ in FIELD_KEYS)
    field_values = [values[key] for key in FIELD_KEYS]
    with get_connection() as connection:
        if equipment_id is None:
            connection.execute(
                f"INSERT INTO equipment (company_id, {fields_sql}) "
                f"VALUES (?, {values_sql})",
                [company_id, *field_values],
            )
        else:
            assignments = ", ".join(f'"{key}" = ?' for key in FIELD_KEYS)
            connection.execute(
                f"UPDATE equipment SET {assignments}, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND company_id = ?",
                [*field_values, equipment_id, company_id],
            )


def delete_equipment(equipment_id, company_id):
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM equipment WHERE id = ? AND company_id = ?",
            (equipment_id, company_id),
        )


def draw_equipment_form(data, prefix):
    values = {}
    for group_name, fields in FIELD_GROUPS.items():
        st.markdown(f"**{group_name}**")
        for start in range(0, len(fields), 2):
            columns = st.columns(2)
            for column, (key, label) in zip(columns, fields[start : start + 2]):
                with column:
                    if key == "fecha_compra":
                        saved_date = data.get(key, "")
                        try:
                            initial_date = date.fromisoformat(saved_date) if saved_date else date.today()
                        except ValueError:
                            initial_date = date.today()
                        has_date = st.checkbox(
                            "Registrar fecha de compra",
                            value=bool(saved_date),
                            key=f"{prefix}_{key}_enabled",
                        )
                        chosen_date = st.date_input(
                            label,
                            value=initial_date,
                            disabled=not has_date,
                            key=f"{prefix}_{key}",
                        )
                        values[key] = chosen_date.isoformat() if has_date else ""
                    elif key in ("observacion", "mantenimiento"):
                        values[key] = st.text_area(
                            label, value=data.get(key, ""), key=f"{prefix}_{key}"
                        )
                    else:
                        values[key] = st.text_input(
                            label, value=data.get(key, ""), key=f"{prefix}_{key}"
                        )
    return values


def record_label(record):
    name = record.get("nombre_equipo") or "Equipo sin nombre"
    serial = record.get("serial") or "Sin serial"
    return f"#{record['id']} · {name} · {serial}"


def show_record_details(record):
    for group_name, fields in FIELD_GROUPS.items():
        with st.expander(group_name):
            columns = st.columns(2)
            for index, (key, label) in enumerate(fields):
                with columns[index % 2]:
                    st.markdown(f"**{label}**")
                    st.write(record.get(key) or "—")


def render_inventory(records):
    st.subheader("Inventario de equipos")
    st.caption("Cada hoja de vida guardada también aparece aquí como un registro del inventario.")
    if not records:
        st.info("Aún no hay equipos registrados.")
        return

    search = st.text_input(
        "Buscar en el inventario",
        placeholder="Nombre, serial, área, asignado o sede",
        key="inventory_search",
    ).strip().casefold()
    filtered = [
        record
        for record in records
        if not search
        or any(search in str(record.get(key, "")).casefold() for key in FIELD_KEYS)
    ]
    st.metric("Equipos registrados", len(records))
    if not filtered:
        st.info("No se encontraron equipos con esa búsqueda.")
        return

    table_rows = []
    for record in filtered:
        row = {"ID": record["id"]}
        row.update(
            {
                label: record.get(key) or "—"
                for key, label in INVENTORY_COLUMNS.items()
            }
        )
        table_rows.append(row)
    st.dataframe(table_rows, hide_index=True, width="stretch")

    selected_id = st.selectbox(
        "Consultar detalle del equipo",
        options=[record["id"] for record in filtered],
        format_func=lambda equipment_id: record_label(
            next(item for item in filtered if item["id"] == equipment_id)
        ),
        key="inventory_detail",
    )
    selected = next(item for item in filtered if item["id"] == selected_id)
    show_record_details(selected)


def render_sheets(records, is_admin, company_id):
    st.subheader("Hojas de vida")
    st.caption("La hoja de vida concentra los datos técnicos, de asignación y mantenimiento de cada equipo.")

    if is_admin:
        with st.expander("Crear hoja de vida", expanded=not records):
            with st.form("create_equipment_form"):
                values = draw_equipment_form({}, "new")
                submitted = st.form_submit_button("Guardar hoja de vida", type="primary")
            if submitted:
                save_equipment(values, company_id)
                st.success("Hoja de vida creada y agregada al inventario.")
                st.rerun()

    if not records:
        st.info("Aún no hay hojas de vida registradas.")
        return

    selected_id = st.selectbox(
        "Seleccionar hoja de vida",
        options=[record["id"] for record in records],
        format_func=lambda equipment_id: record_label(
            next(item for item in records if item["id"] == equipment_id)
        ),
        key="sheet_selected",
    )
    selected = next(item for item in records if item["id"] == selected_id)
    show_record_details(selected)

    if is_admin:
        with st.expander("Modificar hoja de vida"):
            initial_values = {key: selected.get(key, "") for key in FIELD_KEYS}
            with st.form(f"edit_equipment_form_{selected_id}"):
                values = draw_equipment_form(initial_values, f"edit_{selected_id}")
                submitted = st.form_submit_button("Guardar cambios", type="primary")
            if submitted:
                save_equipment(values, company_id, selected_id)
                st.success("Cambios guardados en la hoja de vida y el inventario.")
                st.rerun()

        with st.expander("Eliminar hoja de vida"):
            st.warning("Al eliminarla, el equipo también dejará de aparecer en el inventario.")
            confirmed = st.checkbox(
                f"Confirmo eliminar {record_label(selected)}",
                key=f"confirm_delete_{selected_id}",
            )
            if st.button(
                "Eliminar registro",
                type="secondary",
                disabled=not confirmed,
                key=f"delete_{selected_id}",
            ):
                delete_equipment(selected_id, company_id)
                st.success("Registro eliminado.")
                st.rerun()


def render_company_management():
    with st.sidebar.expander("Agregar empresa"):
        with st.form("create_company_form"):
            company_name = st.text_input("Nombre de la empresa")
            submitted = st.form_submit_button("Agregar empresa")
        if submitted:
            company_name = company_name.strip()
            if not company_name:
                st.sidebar.error("Escribe el nombre de la empresa.")
                return
            if any(
                company["name"].casefold() == company_name.casefold()
                for company in get_companies()
            ):
                st.sidebar.error("Ya existe una empresa con ese nombre.")
                return
            company_id = create_company(company_name)
            st.session_state["company_selected"] = company_id
            st.rerun()


def render_admin_access():
    st.sidebar.header("Acceso")
    if st.session_state.get("is_admin"):
        st.sidebar.success("Sesión de administrador activa")
        if st.sidebar.button("Cerrar sesión"):
            st.session_state.pop("is_admin", None)
            st.rerun()
        render_company_management()
        return True

    if not admin_exists():
        st.sidebar.info("Configura el único usuario administrador.")
        with st.sidebar.form("initial_admin_form"):
            password = st.text_input("Contraseña nueva", type="password")
            confirmation = st.text_input("Confirmar contraseña", type="password")
            submitted = st.form_submit_button("Crear administrador", type="primary")
        if submitted:
            if len(password) < 12:
                st.sidebar.error("La contraseña debe tener al menos 12 caracteres.")
            elif password != confirmation:
                st.sidebar.error("Las contraseñas no coinciden.")
            else:
                create_admin(password)
                st.session_state["is_admin"] = True
                st.rerun()
        return False

    with st.sidebar.form("admin_login_form"):
        st.markdown("**Administrador**")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Iniciar sesión")
    if submitted:
        if authenticate_admin(password):
            st.session_state["is_admin"] = True
            st.rerun()
        else:
            st.sidebar.error("Contraseña incorrecta.")
    st.sidebar.caption("El inventario está disponible en modo de solo lectura.")
    return False


initialize_database()
is_admin = render_admin_access()

st.title("Sistema de inventario")
st.caption("Selecciona la empresa cuyos equipos deseas consultar.")
companies = get_companies()
company_names = {company["id"]: company["name"] for company in companies}
selected_company_id = st.selectbox(
    "Selecciona la empresa que deseas abrir",
    options=list(company_names),
    index=None,
    placeholder="Elige una empresa...",
    format_func=company_names.get,
    key="company_selected",
)
if selected_company_id is None:
    st.info("Selecciona una empresa para consultar su inventario y sus hojas de vida.")
    st.stop()
if selected_company_id not in company_names:
    st.error("La empresa seleccionada no es válida. Elige una empresa de la lista.")
    st.stop()

selected_company_name = company_names[selected_company_id]
header_logo, header_title = st.columns([1, 3])
with header_logo:
    company_logo = COMPANY_LOGOS.get(selected_company_name)
    if company_logo and company_logo.exists():
        st.image(str(company_logo), width=220)

records = get_equipment(selected_company_id)
inventory_tab, sheets_tab = st.tabs(["Inventario", "Hojas de vida"])
with inventory_tab:
    render_inventory(records)
with sheets_tab:
    render_sheets(records, is_admin, selected_company_id)
