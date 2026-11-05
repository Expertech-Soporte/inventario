import hashlib
import hmac
import os
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path

import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "db" / "inventario.db"
COMPANY_DATABASE_DIR = BASE_DIR / "db" / "empresas"
LOGO_PATH = BASE_DIR / "logos" / "Logo-con-Slogan.jpg"
DEJANDO_HUELLA_LOGO_PATH = BASE_DIR / "logos" / "logo-dejando-huella.png"
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


def get_connection(database_path=DATABASE_PATH):
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def company_database_slug(name):
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = "".join(character if character.isalnum() else "-" for character in normalized.lower())
    slug = "-".join(filter(None, slug.split("-")))
    return slug or "empresa"


def initialize_company_database(database_path):
    definitions = ", ".join(f'"{key}" TEXT NOT NULL DEFAULT \'\' ' for key in FIELD_KEYS)
    with get_connection(database_path) as connection:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS equipment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {definitions},
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def get_company_database_path(company_id):
    with get_connection() as connection:
        company = connection.execute(
            "SELECT name, database_file FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
    if company is None:
        return None
    return COMPANY_DATABASE_DIR / (company["database_file"] or f"{company_database_slug(company['name'])}.db")


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
        company_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(companies)")
        }
        if "database_file" not in company_columns:
            connection.execute("ALTER TABLE companies ADD COLUMN database_file TEXT")
        if "logo_file" not in company_columns:
            connection.execute("ALTER TABLE companies ADD COLUMN logo_file TEXT")
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
        legacy_records = [
            dict(row)
            for row in connection.execute("SELECT * FROM equipment").fetchall()
        ]

        used_files = set()
        companies = connection.execute("SELECT id, name, database_file FROM companies ORDER BY id").fetchall()
        for company in companies:
            if company["database_file"]:
                used_files.add(company["database_file"])
                continue
            base_name = company_database_slug(company["name"])
            database_file = f"{base_name}.db"
            suffix = 2
            while database_file in used_files:
                database_file = f"{base_name}-{suffix}.db"
                suffix += 1
            connection.execute(
                "UPDATE companies SET database_file = ? WHERE id = ?",
                (database_file, company["id"]),
            )
            used_files.add(database_file)

        connection.execute(
            "UPDATE companies SET logo_file = ? WHERE name = ? AND logo_file IS NULL",
            (LOGO_PATH.name, "Equipos Gleason S.A."),
        )
        connection.execute(
            "UPDATE companies SET logo_file = ? WHERE name = ? AND logo_file IS NULL",
            (DEJANDO_HUELLA_LOGO_PATH.name, "Dejando Huella Fertilidad"),
        )

    with get_connection() as connection:
        companies = connection.execute(
            "SELECT id, name, database_file FROM companies ORDER BY id"
        ).fetchall()
    for company in companies:
        database_path = COMPANY_DATABASE_DIR / company["database_file"]
        initialize_company_database(database_path)
        records = [
            record
            for record in legacy_records
            if record.get("company_id") == company["id"]
        ]
        if not records:
            continue
        with get_connection(database_path) as company_connection:
            if company_connection.execute("SELECT COUNT(*) FROM equipment").fetchone()[0] > 0:
                continue
            fields_sql = ", ".join(f'"{key}"' for key in FIELD_KEYS)
            placeholders = ", ".join("?" for _ in FIELD_KEYS)
            for record in records:
                company_connection.execute(
                    f"INSERT INTO equipment ({fields_sql}, created_at, updated_at) "
                    f"VALUES ({placeholders}, ?, ?)",
                    [
                        *(record[key] for key in FIELD_KEYS),
                        record.get("created_at", ""),
                        record.get("updated_at", ""),
                    ],
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
                "SELECT id, name, database_file, logo_file FROM companies ORDER BY name COLLATE NOCASE"
            ).fetchall()
        ]


def save_company_logo(uploaded_logo, company_name):
    if uploaded_logo is None:
        return None
    extension = Path(uploaded_logo.name).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("El logo debe ser una imagen PNG, JPG, JPEG o WEBP.")
    logo_directory = BASE_DIR / "logos"
    logo_directory.mkdir(parents=True, exist_ok=True)
    base_name = company_database_slug(company_name)
    logo_file = f"{base_name}{extension}"
    suffix = 2
    while (logo_directory / logo_file).exists():
        logo_file = f"{base_name}-{suffix}{extension}"
        suffix += 1
    logo_path = logo_directory / logo_file
    logo_path.write_bytes(uploaded_logo.getbuffer())
    return logo_file


def get_company_logo(company_id, company_name):
    with get_connection() as connection:
        company = connection.execute(
            "SELECT logo_file FROM companies WHERE id = ?", (company_id,)
        ).fetchone()
    if company and company["logo_file"]:
        logo_path = BASE_DIR / "logos" / company["logo_file"]
        if logo_path.exists():
            return logo_path
    return COMPANY_LOGOS.get(company_name)


def create_company(name, uploaded_logo=None):
    with get_connection() as connection:
        existing_files = {
            row["database_file"]
            for row in connection.execute(
                "SELECT database_file FROM companies WHERE database_file IS NOT NULL"
            )
        }
        base_name = company_database_slug(name.strip())
        database_file = f"{base_name}.db"
        suffix = 2
        while database_file in existing_files:
            database_file = f"{base_name}-{suffix}.db"
            suffix += 1
        logo_file = save_company_logo(uploaded_logo, name.strip())
        cursor = connection.execute(
            "INSERT INTO companies (name, database_file, logo_file) VALUES (?, ?, ?)",
            (name.strip(), database_file, logo_file),
        )
        initialize_company_database(COMPANY_DATABASE_DIR / database_file)
        return cursor.lastrowid


def get_equipment(company_id):
    database_path = get_company_database_path(company_id)
    if database_path is None:
        return []
    with get_connection(database_path) as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT id, "
                + ", ".join(f'"{key}"' for key in FIELD_KEYS)
                + " FROM equipment ORDER BY id DESC"
            ).fetchall()
        ]


def save_equipment(values, company_id, equipment_id=None):
    fields_sql = ", ".join(f'"{key}"' for key in FIELD_KEYS)
    values_sql = ", ".join("?" for _ in FIELD_KEYS)
    field_values = [values[key] for key in FIELD_KEYS]
    database_path = get_company_database_path(company_id)
    if database_path is None:
        return
    with get_connection(database_path) as connection:
        if equipment_id is None:
            connection.execute(
                f"INSERT INTO equipment ({fields_sql}) VALUES ({values_sql})",
                field_values,
            )
        else:
            assignments = ", ".join(f'"{key}" = ?' for key in FIELD_KEYS)
            connection.execute(
                f"UPDATE equipment SET {assignments}, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                [*field_values, equipment_id],
            )


def delete_equipment(equipment_id, company_id):
    database_path = get_company_database_path(company_id)
    if database_path is None:
        return
    with get_connection(database_path) as connection:
        connection.execute(
            "DELETE FROM equipment WHERE id = ?",
            (equipment_id,),
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
            company_logo = st.file_uploader(
                "Logo de la empresa",
                type=["png", "jpg", "jpeg", "webp"],
            )
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
            try:
                company_id = create_company(company_name, company_logo)
            except ValueError as error:
                st.sidebar.error(str(error))
                return
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
    company_logo = get_company_logo(selected_company_id, selected_company_name)
    if company_logo and company_logo.exists():
        st.image(str(company_logo), width=220)

records = get_equipment(selected_company_id)
inventory_tab, sheets_tab = st.tabs(["Inventario", "Hojas de vida"])
with inventory_tab:
    render_inventory(records)
with sheets_tab:
    render_sheets(records, is_admin, selected_company_id)
