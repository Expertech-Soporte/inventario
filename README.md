# Inventario Equipos Gleason

Aplicación local de inventario y hojas de vida hecha con Streamlit. Cada hoja de
vida se guarda como el registro del equipo y sus datos aparecen también en el
inventario.

## Requisitos

- Python 3.10 o superior

## Instalación y ejecución en Windows

Desde esta carpeta, en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1
```

En el primer inicio, crea la contraseña del único usuario `admin` desde la
barra lateral. Debe tener al menos 12 caracteres. No existe registro de otros
usuarios: quien no inicia sesión puede consultar, pero no crear, modificar ni
eliminar equipos.

Al abrir la aplicación, selecciona una empresa de la lista para consultar sus
equipos. El administrador puede agregar empresas desde la opción **Agregar
empresa** de la barra lateral. Cada empresa tiene su propio inventario y hojas
de vida; los registros que ya existían quedan asignados a **Equipos Gleason
S.A.**. La lista incluye **Dejando Huella Fertilidad**, con su logo al
seleccionarla.

Para permitir consultas desde otros computadores de la misma red, inicia
Streamlit con `python -m streamlit run app.py --server.address 0.0.0.0` y limita
el acceso mediante la red y el firewall de la empresa. El acceso de lectura no
solicita contraseña; no publiques esta aplicación directamente en Internet.

Los datos se guardan en `inventario.db` junto a la aplicación. Mantén una copia
de seguridad de ese archivo. La contraseña del administrador se almacena como
un hash con salt; no se guarda en texto plano.

## Campos de la hoja de vida

Proveedor, entrada/factura, nombre y tipo de equipo, área, asignado, cargo,
sede, modelo, marca, serial del equipo, disco, procesador, RAM, tarjeta gráfica,
modelo y serial del monitor, sistema operativo, licencia Office, serial de
licencia, tenant, correo ENTRA ID, usuario, servidor, fecha de compra, garantía,
observación, ID RUSTDESK y mantenimiento.
