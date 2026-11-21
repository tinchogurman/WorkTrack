# WorkTrack

Time tracker personal, local y gratuito para Windows (estilo Toggl/Clockify).
Sin servicios externos: todo queda en una base SQLite en tu equipo.

> Estado: **Fases 1, 2 y 3 completas** — Timer, proyectos y tareas, historial con filtros, recuperación ante
> cierres inesperados, detección de suspensión, Dashboard, Reports con exportación a Excel/CSV, bandeja del
> sistema, Settings, backups seguros y ejecutable para Windows.
> La especificación completa está en [SPEC.md](SPEC.md).

## Requisitos

- Windows 10/11
- Python 3.12 o superior (desarrollado con 3.14)
- git

## Instalación

```powershell
git clone <repo> WorkTrack
cd WorkTrack
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements.txt` contiene solo las dependencias de ejecución; `requirements-dev.txt` agrega las de pruebas
y PyInstaller. Se usa `PySide6-Essentials` (QtCore/QtGui/QtWidgets), no el paquete `PySide6` completo: no instales ambos.

## Ejecución

```powershell
.\.venv\Scripts\pythonw.exe -m worktrack     # sin consola
.\.venv\Scripts\python.exe  -m worktrack     # con consola (ve el log en vivo)
```

## Ejecutable para Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

El script corre las pruebas (si alguna falla, no construye), regenera el ícono (`tools/make_icon.py` →
`assets/worktrack.ico`) y ejecuta PyInstaller con la configuración versionada [WorkTrack.spec](WorkTrack.spec).
Resultado: la carpeta `dist\WorkTrack\` (~160 MB) con `WorkTrack.exe` (sin consola). Para usarla, copiá la carpeta
completa donde quieras (por ejemplo `C:\Programas\WorkTrack`) y creá un acceso directo a `WorkTrack.exe`.
Los datos no viajan con el ejecutable: siempre están en `%APPDATA%\WorkTrack`, así que actualizar la app
(reemplazar la carpeta) no toca tu información; la base se migra automáticamente si cambia de versión.

Para que arranque con Windows, poné un acceso directo a `WorkTrack.exe` en la carpeta que abre `Win+R` →
`shell:startup` (y activá "Iniciar minimizado" en Settings).

## Uso

**Timer**
1. Elegí un proyecto y escribí o elegí una tarea (si la tarea no existe, se crea al iniciar).
2. Opcional: una descripción.
3. **▶ Play** (o `Enter` en el campo de tarea, o `Ctrl+Espacio`). La sesión se guarda en la base en ese mismo instante.
4. Podés minimizar: el tiempo se calcula desde la hora real de inicio, no con un contador. El título de la ventana y el ícono de la barra de tareas muestran que hay una sesión en curso.
5. **■ Stop** (o `Ctrl+Espacio`) detiene y guarda. Para cambiar de tarea, primero detené la sesión.

**Projects**: crear, editar, color, archivar/desarchivar proyectos y tareas. Un proyecto o tarea con sesiones no se puede eliminar, solo archivar; los archivados no se ofrecen en Timer pero su historial se conserva.

**History**: tabla ordenable (clic en el encabezado). `+ Agregar sesión` (`Ctrl+N`) para cargar una sesión olvidada; doble clic / `Enter` para editar; `Supr` para eliminar (con confirmación). El diálogo muestra la duración resultante antes de guardar.
Filtros por período (Todo, Hoy, Esta semana, Este mes, Últimos 30 días, Este año o rango personalizado), proyecto y tarea.
El filtro de fechas muestra las sesiones que se *solapan* con el rango: una sesión de 23:00 a 01:00 aparece filtrando cualquiera de los dos días. Si una sesión termina otro día, la hora de fin se marca `(+1)`.

**Dashboard**: horas de hoy, esta semana y este mes; para el período elegido, total, sesiones, promedio diario (sobre días con actividad) y proyecto con mayor dedicación. Gráficos de horas por día, por semana, evolución de 12 meses y distribución por proyecto y por tarea (pasá el mouse sobre una barra para ver el detalle). La sesión en curso se cuenta hasta el momento actual.

**Reports**: reporte por día, semana, mes o rango personalizado, filtrable por proyecto y tarea. Muestra total (HH:MM:SS y horas decimales), sesiones, días con actividad y desgloses por proyecto, tarea, día, semana y el detalle de sesiones. Solo incluye sesiones finalizadas.
- **Exportar Excel** (`.xlsx`): hojas Resumen, Por proyecto, Por tarea, Por día, Por semana y Sesiones. Las duraciones son tiempos de Excel (`[h]:mm:ss`) y las horas decimales son números, así se pueden sumar en la planilla.
- **Exportar CSV**: el detalle de sesiones, con separador `;`, coma decimal (`1,50`) y UTF-8 con BOM (se abre directo en Excel en español).

### Semanas, días y sesiones que cruzan la medianoche

- Las semanas van de **lunes a domingo**.
- El historial guarda cada sesión como un único registro, pero los totales por día, semana y mes (Dashboard y Reports) **reparten** la duración entre los días que toca, cortando en la medianoche **local**. Ej.: 23:00–01:00 suma 1 h a cada día.
- En Reports, la pestaña/hoja *Sesiones* muestra cada sesión completa y la columna *En el período* indica la parte que cae dentro del rango, para que el detalle cuadre con los totales.

**Settings**: inicio minimizado, minimizar a la bandeja, confirmación al salir con una sesión en curso (si
la desactivás, al salir la sesión se detiene y se guarda), formato horario 12/24 h (solo pantalla; las
exportaciones usan 24 h), carpeta de exportación y copias de seguridad. Los cambios se guardan al instante en
`%APPDATA%\WorkTrack\settings.json` (fuera de la base: restaurar un backup no cambia tus preferencias).

**Bandeja del sistema**: el ícono se pone verde con ▶ mientras hay una sesión; el tooltip muestra el tiempo y
la tarea. Menú: *Abrir WorkTrack*, *Detener sesión*, *Salir*. El botón minimizar envía la ventana a la bandeja
(configurable); la X cierra la aplicación.

**Atajos**: `Ctrl+1…6` cambia de sección, `Ctrl+Espacio` inicia/detiene.

### Suspensión e interrupciones

WorkTrack distingue tiempo transcurrido de tiempo trabajado. Si durante una sesión Windows se suspende
(evento de energía) o la aplicación pasa **5 minutos o más** sin su latido de 30 s (equipo dormido o congelado),
aparece un aviso en Timer (y una notificación en la bandeja) con inicio, fin y duración del intervalo:

- **Conservar**: el tiempo se sigue contando.
- **Descontar**: se resta el intervalo detectado.
- **Corregir…**: elegís el tramo exacto a descontar.

**Nunca se descuenta nada sin tu confirmación.** Si presionás Stop con un aviso pendiente, primero se pregunta
(cerrar el diálogo = conservar). Lo descontado queda registrado (tabla `session_interruptions`) y los totales por
día excluyen exactamente ese tramo. Todo queda en el log.

### Copias de seguridad

En Settings → *Crear backup ahora* genera `%APPDATA%\WorkTrack\backups\worktrack_AAAAMMDD_HHMMSS.db` con la API
de backup de SQLite (copia consistente aunque la app esté en uso). Para restaurar (*Restaurar seleccionado…* o
*desde archivo…*): la app rechaza la restauración si hay una sesión en curso, valida el archivo (SQLite válido,
`integrity_check`, tablas de WorkTrack, versión de esquema), pide confirmación, **crea automáticamente un backup
del estado actual** (`pre-restore_…db`), cierra las conexiones, restaura y reabre. Si algo falla, vuelve al
estado anterior. Los backups nunca se borran automáticamente.

### Reglas de consistencia

- Solo puede haber **una sesión activa** (garantizado también por la base de datos).
- La tarea de una sesión **pertenece a su proyecto** (clave foránea compuesta).
- Fin posterior al inicio, sin fechas futuras, duración nunca negativa.
- **Sin superposiciones**: una sesión no puede pisar a otra. Sesiones contiguas (una termina justo cuando empieza la otra) son válidas. La sesión activa ocupa el rango `[inicio, ahora]`.
- Al editar inicio/fin, la duración se recalcula como `fin − inicio`.
- Las sesiones de más de 12 h piden confirmación.

### Cierre inesperado

Mientras hay una sesión activa, la app guarda cada 30 s un "latido" (último momento en que estaba funcionando).
Si WorkTrack se cierra de golpe (corte de luz, proceso terminado), al reabrirla aparece un diálogo que muestra
desde cuándo está activa la sesión y cuándo fue el último latido, y permite:

- **Finalizar en el último momento conocido** (opción por defecto),
- **Finalizar a una hora indicada**, o
- **Continuar** la sesión (cuenta todo hasta ahora).

Al salir normalmente con una sesión activa, la app pregunta si detenerla o dejarla en curso.

## Datos

| Qué | Dónde |
|---|---|
| Base de datos | `%APPDATA%\WorkTrack\worktrack.db` |
| Preferencias | `%APPDATA%\WorkTrack\settings.json` |
| Backups | `%APPDATA%\WorkTrack\backups\` |
| Logs (rotativos) | `%APPDATA%\WorkTrack\logs\worktrack.log` |

Fuera del repositorio y del ejecutable. Las marcas de tiempo se guardan en UTC (`YYYY-MM-DDTHH:MM:SSZ`)
y se muestran en la hora local. La variable de entorno `WORKTRACK_DATA_DIR` permite usar otra carpeta (la usan las pruebas).

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Las pruebas de interfaz corren sin ventana (`QT_QPA_PLATFORM=offscreen`) y nunca tocan `%APPDATA%`.

## Arquitectura

```
worktrack/
├── app.py              arranque: logging, preferencias, instancia única, BD, recuperación, ventana,
│                       bandeja, eventos de energía
├── paths.py            ubicación de datos
├── settings.py         preferencias (JSON)
├── core/               modelos, errores de dominio, reloj inyectable, intervalos, utilidades de tiempo
├── db/                 conexión (foreign_keys=ON, WAL), esquema, migraciones, traducción de errores
├── repositories/       SQL parametrizado, sin reglas de negocio
├── analytics/          prorrateo por día local, períodos, segmentos y agregaciones (pandas)
├── services/           reglas de negocio (sin Qt): proyectos, timer, historial, recuperación,
│                       interrupciones, dashboard, reportes, exportación (openpyxl / csv) y backups
└── ui/                 PySide6: tema, ventana principal, vistas, diálogos, gráficos (PyQtGraph),
                        bandeja y filtro nativo WM_POWERBROADCAST
tests/                  pytest + pytest-qt
tools/make_icon.py      genera assets/worktrack.ico
launcher.py             punto de entrada del ejecutable
WorkTrack.spec          configuración de PyInstaller (versionada)
build.ps1               pruebas + ícono + build
```

Capas: `ui → services → repositories → db`. Los servicios no dependen de Qt y reciben un reloj inyectable,
lo que permite probar el paso del tiempo de forma determinista.

**Esquema** (`worktrack/db/schema.py`, versionado con `PRAGMA user_version`):
`projects`, `tasks` y `time_entries`. Restricciones a nivel base de datos: índice único parcial
`ux_single_active` (una sola fila con `end_time IS NULL`), FK compuesta `(task_id, project_id) → tasks(id, project_id)`,
`CHECK` nombrados para duraciones y formato de fechas, `ON DELETE RESTRICT`.
`duration_seconds` es tiempo *trabajado*: `fin − inicio − tramos descontados`. La versión 2 del esquema agrega
`session_interruptions` (intervalo detectado, estado `pending/kept/discounted/adjusted` y tramo descontado,
`ON DELETE CASCADE` con la sesión). Esa tabla es la base natural para una futura función de Pausa/Reanudar
(sección 16 del SPEC): una pausa sería un tramo descontado creado por el usuario.

Los errores de integridad de SQLite se traducen a mensajes claros (`worktrack/db/errors.py`); la interfaz nunca
muestra errores crudos y los inesperados se registran en el log.

**Analytics**: `analytics/proration.py` corta cada sesión en la medianoche local (aritmética en UTC, correcta
también con horario de verano), excluye exactamente los tramos descontados y reparte el resto con redondeo de
mayor resto, de modo que la suma por días es siempre igual a la duración guardada. Los servicios reciben la zona
horaria (`tz=None` = la del sistema); las pruebas usan zonas explícitas.

**Agregar una migración**: añadir el script a `MIGRATIONS` en `worktrack/db/migrations.py`; se aplica en una
transacción al abrir la base (también al restaurar un backup de una versión anterior).

## Criterios de aceptación (SPEC §13)

| # | Escenario | Verificación |
|---|---|---|
| 1–2 | Iniciar, detener y duración correcta | `tests/test_timer_service.py`, `tests/test_ui.py::test_play_stop_from_ui` |
| 3–4 | Cerrar/reabrir y el historial persiste | `tests/test_recovery.py::test_history_survives_reopen`; app real abierta y cerrada |
| 5 | Cierre inesperado y recuperación | `tests/test_recovery.py`; proceso real (script y `.exe`) terminado a la fuerza y reabierto |
| 5b | La BD rechaza una 2.ª sesión activa | `tests/test_schema.py::test_second_active_session_rejected_by_database` |
| 5c | Sesión que cruza medianoche | `tests/test_proration.py`, `tests/test_analytics.py` |
| 5d | Suspensión detectada y no descontada sin confirmación | `tests/test_interruptions.py`, `tests/test_ui.py` |
| 5e | Backup, restauración y backup previo | `tests/test_backup.py`, `tests/test_ui.py::test_settings_backup_and_restore_from_ui` |
| 6–7 | Dos proyectos; totales del dashboard = registros | `tests/test_analytics.py::test_dashboard_totals_match_records` |
| 8 | Editar una sesión | `tests/test_entry_service.py`, `tests/test_ui.py::test_entry_dialog_edit_recalculates` |
| 9 | Exportar Excel y verificar | `tests/test_exporters.py` (relee el .xlsx con openpyxl) |
| 10 | El ejecutable inicia | `.exe` arrancado, navegado por todas las secciones y cerrado (código 0) |
