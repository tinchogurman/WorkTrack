# WorkTrack

Time tracker personal, local y gratuito para Windows (estilo Toggl/Clockify).
Sin servicios externos: todo queda en una base SQLite en tu equipo.

> Estado: **Fase 2 (Analytics)** — Timer, proyectos y tareas, historial con filtros, recuperación ante
> cierres inesperados, Dashboard y Reports con exportación a Excel/CSV.
> Bandeja del sistema, Settings, backups, detección de suspensión y `.exe` llegan en la Fase 3.
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

`requirements.txt` contiene solo las dependencias de ejecución; `requirements-dev.txt` agrega las de pruebas.
Se usa `PySide6-Essentials` (QtCore/QtGui/QtWidgets), no el paquete `PySide6` completo: no instales ambos.

## Ejecución

```powershell
.\.venv\Scripts\pythonw.exe -m worktrack     # sin consola
.\.venv\Scripts\python.exe  -m worktrack     # con consola (ve el log en vivo)
```

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

**Atajos**: `Ctrl+1…6` cambia de sección, `Ctrl+Espacio` inicia/detiene.

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
├── app.py              arranque: logging, instancia única, BD, recuperación, ventana
├── paths.py            ubicación de datos
├── core/               modelos, errores de dominio, reloj inyectable, utilidades de tiempo
├── db/                 conexión (foreign_keys=ON, WAL), esquema, migraciones, traducción de errores
├── repositories/       SQL parametrizado, sin reglas de negocio
├── analytics/          prorrateo por día local, períodos, segmentos y agregaciones (pandas)
├── services/           reglas de negocio (sin Qt): proyectos, timer, historial, recuperación,
│                       dashboard, reportes y exportación (openpyxl / csv)
└── ui/                 PySide6: tema, ventana principal, vistas, diálogos, gráficos (PyQtGraph)
tests/                  pytest + pytest-qt
```

Capas: `ui → services → repositories → db`. Los servicios no dependen de Qt y reciben un reloj inyectable,
lo que permite probar el paso del tiempo de forma determinista.

**Esquema** (`worktrack/db/schema.py`, versionado con `PRAGMA user_version`):
`projects`, `tasks` y `time_entries`. Restricciones a nivel base de datos: índice único parcial
`ux_single_active` (una sola fila con `end_time IS NULL`), FK compuesta `(task_id, project_id) → tasks(id, project_id)`,
`CHECK` nombrados para duraciones y formato de fechas, `ON DELETE RESTRICT`.
`duration_seconds` es tiempo *trabajado* y puede ser menor que `fin − inicio`: deja lugar para descontar
suspensiones (Fase 3) y para una futura tabla de pausas sin cambiar el esquema.

Los errores de integridad de SQLite se traducen a mensajes claros (`worktrack/db/errors.py`); la interfaz nunca
muestra errores crudos y los inesperados se registran en el log.

**Analytics**: `analytics/proration.py` corta cada sesión en la medianoche local (aritmética en UTC, correcta
también con horario de verano) y reparte el tiempo trabajado proporcionalmente con redondeo de mayor resto, de
modo que la suma por días es siempre exacta. Los servicios reciben la zona horaria (`tz=None` = la del sistema);
las pruebas usan zonas explícitas.

**Agregar una migración**: añadir el script a `MIGRATIONS` en `worktrack/db/migrations.py`; se aplica en una
transacción al abrir la base.
