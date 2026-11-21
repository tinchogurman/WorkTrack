Proyecto: WorkTrack — Personal Time Tracker

Actuá como un Senior Python Developer y Software Architect, especializado en aplicaciones de escritorio para Windows.

Quiero que desarrolles desde cero una aplicación llamada WorkTrack, un sistema personal de seguimiento de horas trabajadas (Time Tracking), similar a Toggl Track o Clockify.

La aplicación debe ser completamente funcional, gratuita, local y sin depender de servicios externos.

No quiero una maqueta ni un prototipo visual. Quiero una aplicación real que pueda utilizar diariamente en mi computadora con Windows 11.

Este archivo (SPEC.md) es la especificación de referencia del proyecto. Releelo al comenzar cada fase y cada nueva sesión de trabajo.

0. Reglas de trabajo (leer antes de empezar)
Carpeta del proyecto: usá la carpeta actual (WorkTrack) como raíz del proyecto. No crees una subcarpeta WorkTrack adentro.
Plan antes de código: antes de escribir código de cada fase, mostrame el plan (estructura de carpetas, modelo de datos, módulos y pasos) y esperá mi aprobación.
Frenar entre fases: al terminar cada fase, detenete, resumime qué hiciste, qué pruebas pasaron y qué queda pendiente, y esperá mi confirmación antes de pasar a la siguiente.
Control de versiones: inicializá un repositorio git al comenzar, con un .gitignore adecuado para Python (.venv/, __pycache__/, .pytest_cache/, build/, dist/, logs, *.db, *.sqlite, backups y exportaciones). Hacé un commit con un mensaje descriptivo al terminar cada paso funcional.
Nunca incluyas en los commits datos personales, bases de datos, backups, exportaciones (.xlsx/.csv con datos reales), logs ni credenciales. Revisá git status antes de cada commit.
El archivo .spec de PyInstaller sí debe versionarse si se usa para configurar el empaquetado (no ignores todos los *.spec), para que el build sea reproducible.
Seguridad: no modifiques proyectos existentes fuera de esta carpeta ni elimines archivos sin autorización.
1. Objetivo principal

Necesito registrar cuánto tiempo dedico a diferentes proyectos y tareas.

El funcionamiento debe ser sencillo:

Selecciono un proyecto.
Escribo o selecciono una tarea.
Presiono Play (▶).
El cronómetro comienza a contabilizar el tiempo en formato HH:MM:SS.
Mientras el cronómetro está activo, puedo minimizar la aplicación y continuar trabajando.
Cuando termino, presiono Stop (■).
La aplicación guarda automáticamente la sesión.
Posteriormente puedo consultar cuánto tiempo trabajé por tarea, proyecto, día, semana o mes.

El objetivo es poder llevar un registro histórico de mis actividades y generar reportes de productividad.

2. Stack tecnológico

Utilizá las siguientes tecnologías:

Python 3: lenguaje principal.
PySide6 (Qt): interfaz gráfica de escritorio.
SQLite: base de datos local.
Pandas: procesamiento y análisis de datos.
OpenPyXL: exportación a Excel.
PyQtGraph: gráficos estadísticos (integración nativa con PySide6). Si algún gráfico concreto (por ejemplo, torta/distribución) resulta claramente mejor con Matplotlib, consultame antes de agregarlo como dependencia.
PyInstaller: generación de ejecutable para Windows.
Pytest: pruebas automatizadas.

Priorizá una arquitectura sencilla, modular, mantenible y fácil de ampliar.

No utilices servicios pagos, APIs externas ni infraestructura cloud.

3. Cronómetro (funcionalidad principal)

Implementá un cronómetro con las siguientes características:

Botón Play para iniciar.
Botón Stop para detener y guardar.
Visualización HH:MM:SS.
Proyecto y tarea asociados a cada sesión.
Indicador visual de cronómetro activo.
Solo una sesión activa simultáneamente.
Posibilidad de cambiar de tarea deteniendo primero la sesión actual.

Requisito técnico fundamental:

El cronómetro no debe depender de incrementar un contador cada segundo.

Debe registrar la fecha y hora real de inicio y calcular el tiempo transcurrido a partir de timestamps.

Esto permitirá que el cronómetro siga contabilizando correctamente mientras la aplicación esté minimizada.

Cuando se inicia una sesión, debe guardarse inmediatamente en SQLite, no únicamente cuando se presiona Stop.

Si la aplicación se cierra inesperadamente y vuelve a abrirse, debe detectar la sesión activa y ofrecer continuarla o finalizarla.

3.1 Tiempo transcurrido vs. tiempo trabajado

La aplicación debe distinguir entre tiempo transcurrido y tiempo efectivamente trabajado. Ejemplo: si inicio el cronómetro a las 14:00, Windows se suspende a las 15:00 y vuelvo a las 18:00, la aplicación no debe asumir silenciosamente que trabajé cuatro horas.

Detectá, cuando sea técnicamente posible, períodos de suspensión/reanudación de Windows o interrupciones prolongadas (por ejemplo, un salto grande entre dos "latidos" consecutivos del cronómetro, o eventos de energía del sistema).
Al detectar un intervalo sospechoso, informalo indicando su inicio, fin y duración aproximados.
No descontés automáticamente esos períodos sin mi confirmación. Permití: conservar el tiempo, descontar el intervalo detectado o corregir manualmente.
Lo mismo aplica a la recuperación tras un cierre inesperado: al reabrir, mostrar desde cuándo está activa la sesión y cuándo fue el último momento en que la aplicación estuvo funcionando, y permitir continuar, finalizar en ese último momento conocido o finalizar en una hora que yo indique.
Registrá en el log las detecciones de suspensión y recuperaciones.
4. Gestión de proyectos y tareas

La aplicación debe permitir:

Crear proyectos.
Editar proyectos.
Archivar proyectos.
Asignar colores a proyectos.
Crear tareas asociadas a proyectos.
Reutilizar tareas existentes.
Agregar una descripción opcional a cada sesión.

Ejemplos de proyectos:

Data Engineering
Desarrollo Python
Estudio y capacitación
Trabajo freelance
Actividades administrativas
Proyectos personales

Cada proyecto puede contener múltiples tareas.

Integridad entre proyectos y tareas:

Verificá que la tarea de cada sesión pertenezca al proyecto seleccionado, tanto en la lógica de negocio como en la base de datos (ver sección 9).
Un proyecto archivado no se ofrece para nuevas sesiones, pero sus sesiones históricas se conservan y siguen apareciendo en historial y reportes.
No se puede eliminar un proyecto o una tarea que tenga sesiones registradas: solo archivarlo. La eliminación física solo se permite si no tiene sesiones asociadas, con confirmación.
5. Historial de sesiones

Crear una sección llamada History.

Debe mostrar una tabla con:

Campo	Descripción
Fecha	Día de la sesión
Proyecto	Proyecto asociado
Tarea	Actividad realizada
Inicio	Hora de inicio
Fin	Hora de finalización
Duración	Tiempo trabajado
Descripción	Notas opcionales

Funcionalidades:

Filtrar por fechas.
Filtrar por proyecto.
Filtrar por tarea.
Ordenar registros.
Editar sesiones.
Eliminar sesiones con confirmación.
Agregar sesiones manualmente cuando olvide iniciar el cronómetro.

Validar que las duraciones sean correctas y evitar registros inconsistentes.

6. Dashboard de productividad

Crear una sección llamada Dashboard.

Debe incluir:

Indicadores principales:

Horas trabajadas hoy.
Horas trabajadas esta semana.
Horas trabajadas este mes.
Cantidad de sesiones.
Promedio de horas diarias.
Proyecto con mayor dedicación.

Visualizaciones:

Horas trabajadas por día.
Horas trabajadas por semana.
Distribución de horas por proyecto.
Distribución de horas por tarea.
Evolución mensual del tiempo trabajado.

Permitir seleccionar períodos personalizados.

Los gráficos deben actualizarse a partir de los datos almacenados en SQLite.

Sesiones que cruzan medianoche: el historial conserva la sesión como un único registro, pero los totales diarios, semanales y mensuales (dashboard y reportes) deben prorratear la duración entre los días correspondientes. Ejemplo: una sesión de 23:00 a 01:00 suma 1 hora al primer día y 1 hora al segundo. El corte de día debe hacerse en la zona horaria local, no en UTC. Incluí pruebas unitarias para este caso (incluyendo sesiones que abarcan más de dos días y cortes de semana/mes).

7. Reportes y exportaciones

Crear una sección llamada Reports.

Debe permitir generar reportes por:

Día.
Semana.
Mes.
Rango personalizado.
Proyecto.
Tarea.

Incluir:

Total de horas.
Desglose por proyecto.
Desglose por tarea.
Cantidad de sesiones.
Detalle de inicio y finalización.

Permitir exportar a:

Excel (.xlsx).
CSV.

Los totales por día/semana/mes de los reportes aplican el mismo prorrateo de sesiones que cruzan medianoche descrito en la sección 6; el detalle de sesiones muestra cada sesión completa.

Los reportes deben incluir tanto la duración en HH:MM:SS como las horas decimales, útiles para facturación.

Ejemplo: 1 hora y 30 minutos = 1,50 horas.

8. Interfaz gráfica

Quiero una interfaz moderna, profesional y fácil de utilizar.

Inspirate en aplicaciones de productividad como Toggl Track o Clockify, sin copiar literalmente su diseño.

Diseño deseado:

Tema oscuro.
Tipografía clara.
Cronómetro grande y visible.
Botón Play destacado en verde.
Botón Stop destacado en rojo.
Navegación lateral.
Tablas legibles.
Gráficos modernos.
Interfaz completamente funcional con mouse y teclado.

Secciones principales:

Timer
Dashboard
Projects
History
Reports
Settings

La aplicación debe permitir minimizarse a la bandeja del sistema de Windows.

Mientras exista una sesión activa, el icono de la bandeja debe indicar que el cronómetro está funcionando.

El menú de la bandeja debe permitir abrir la ventana y detener la sesión activa.

9. Base de datos y persistencia

Utilizar SQLite.

Diseñar un esquema relacional adecuado, incluyendo como mínimo:

projects

id
name
color
archived
created_at

tasks

id
project_id
name
description
created_at

time_entries

id
project_id
task_id
start_time
end_time
duration_seconds
description
created_at

Utilizar claves foráneas e índices apropiados.

Reglas de integridad a nivel base de datos (no depender solo de la interfaz):

Ejecutar PRAGMA foreign_keys = ON en todas las conexiones.
Una única sesión activa: índice único parcial que impida más de una fila con end_time IS NULL en time_entries (por ejemplo, CREATE UNIQUE INDEX ... ON time_entries((1)) WHERE end_time IS NULL). Debe funcionar aunque falle la interfaz. Incluí una prueba que intente insertar dos sesiones activas y verifique que falla.
Tarea del proyecto correcto: garantizar que time_entries.task_id pertenezca a time_entries.project_id (por ejemplo, con una clave foránea compuesta hacia tasks(id, project_id) y su UNIQUE correspondiente, o un trigger).
Duraciones válidas: CHECK que impida end_time anterior a start_time y duration_seconds negativa.
Definir explícitamente el comportamiento ON DELETE (por ejemplo, RESTRICT para proyectos y tareas con sesiones).

Los timestamps deben almacenarse de forma consistente, preferentemente en UTC, y mostrarse en la zona horaria local.

Las sesiones activas tendrán end_time NULL.

La base de datos debe almacenarse en una ubicación persistente dentro del directorio de datos del usuario de Windows (por ejemplo, %APPDATA%\WorkTrack), no en una carpeta temporal, no dentro del ejecutable y no dentro del repositorio git.

No perder información al cerrar o actualizar la aplicación.

10. Configuración

Crear una sección Settings con:

Preferencia de inicio minimizado.
Minimizar a la bandeja.
Confirmación antes de salir con una sesión activa.
Formato horario.
Carpeta predeterminada de exportación.
Copia de seguridad de la base de datos.
Restauración desde backup, con confirmación.

Backups seguros:

No copiar directamente el archivo .db mientras la aplicación está en uso. Utilizar la API de backup de SQLite (sqlite3.Connection.backup) para generar copias consistentes.
Antes de restaurar: validar que el archivo sea una base SQLite válida de WorkTrack (PRAGMA integrity_check y presencia de las tablas esperadas), generar automáticamente un backup del estado actual, cerrar las conexiones abiertas, y solo entonces restaurar.
No permitir restaurar mientras haya una sesión activa sin antes resolverla.
Los backups se guardan fuera del repositorio git.
11. Calidad del software

Implementar:

Manejo adecuado de errores.
Validación de entradas.
Consultas SQL parametrizadas.
Separación entre interfaz, lógica de negocio y persistencia.
Registro de errores en archivos de log.
Pruebas unitarias.
Prevención de sesiones activas duplicadas.
Prevención de duraciones negativas.
Recuperación ante cierres inesperados.

No es necesario implementar autenticación ni múltiples usuarios en esta primera versión.

12. Instalación y ejecución

Mi computadora utiliza Windows 11.

Quiero que:

Inspecciones el entorno de desarrollo disponible (versión de Python, pip, git).
Uses la carpeta actual (WorkTrack) como raíz del proyecto e inicialices un repositorio git.
Configures un entorno virtual Python (.venv) dentro de la carpeta del proyecto.
Instales las dependencias necesarias y las registres en requirements.txt.
Desarrolles la aplicación.
Ejecutes las pruebas automatizadas.
Corrijas los errores detectados.
Inicies la aplicación para comprobar su funcionamiento.
Prepares un ejecutable .exe utilizando PyInstaller.
Generes un README con instrucciones de instalación, ejecución y uso.

No modifiques proyectos existentes ni elimines archivos sin autorización.

13. Criterios de aceptación

Antes de considerar terminado el proyecto, verificá estos escenarios:

Iniciar una sesión y detenerla después de varios segundos.
Confirmar que la duración registrada es correcta.
Cerrar y volver a abrir la aplicación.
Confirmar que el historial permanece guardado.
Iniciar una sesión, cerrar inesperadamente la aplicación y comprobar su recuperación. 5b. Confirmar que la base de datos rechaza una segunda sesión activa aunque se intente insertar directamente. 5c. Registrar una sesión que cruce medianoche y verificar que los totales diarios se reparten correctamente. 5d. Simular (en pruebas) una suspensión durante una sesión activa y verificar que se detecta y no se descuenta sin confirmación. 5e. Generar un backup, restaurarlo y verificar que antes se creó un backup del estado previo.
Crear dos proyectos diferentes y registrar sesiones para ambos.
Comprobar que los totales del dashboard coinciden con los registros.
Editar manualmente una sesión.
Exportar un reporte Excel y verificar sus resultados.
Confirmar que el ejecutable puede iniciarse correctamente.

Si alguna prueba no puede realizarse automáticamente, indicá claramente cuál queda pendiente de validación manual.

14. Metodología de desarrollo

Trabajá de forma incremental.

Fase 1 — MVP obligatorio

Interfaz principal.
Cronómetro Play/Stop.
Proyectos y tareas.
Persistencia SQLite.
Historial básico.

Fase 2 — Analytics

Dashboard.
Estadísticas.
Filtros.
Reportes CSV/Excel.

Fase 3 — Experiencia de escritorio

Bandeja del sistema.
Configuración.
Backups.
Ejecutable Windows.

Priorizá terminar y probar correctamente cada fase antes de avanzar a la siguiente.

No sacrifiques estabilidad por agregar funcionalidades secundarias. El objetivo principal es un MVP estable que registre horas correctamente; no amplíes el alcance más allá de este documento.

Distribución de los requisitos de integridad: la sesión activa única, la integridad proyecto/tarea, los CHECK de duración y la recuperación tras cierre inesperado son parte de la Fase 1. El prorrateo por medianoche es parte de la Fase 2. La detección de suspensión y los backups seguros son parte de la Fase 3 (dejar el diseño preparado desde la Fase 1).

Para cada fase:

Mostrame el plan y esperá mi aprobación.
Implementá, haciendo commits en cada paso funcional.
Ejecutá las pruebas y corregí errores.
Detenete y presentame un resumen: qué se hizo, qué pruebas pasaron, qué queda pendiente de validación manual.
Esperá mi confirmación antes de continuar con la fase siguiente.
15. Resultado esperado

Al finalizar quiero tener:

Una aplicación de escritorio funcional.
Un cronómetro confiable.
Proyectos y tareas configurables.
Historial persistente.
Reportes de horas trabajadas.
Dashboard de productividad.
Código fuente organizado.
Pruebas automatizadas.
Un ejecutable para Windows.
Documentación para continuar desarrollándola.
16. Fuera de alcance (posibles mejoras futuras)

No implementar en esta versión, pero no tomar decisiones de diseño que lo impidan:

Botón Pausa / Reanudar para registrar descansos sin fragmentar una tarea en múltiples sesiones (probablemente mediante una tabla de pausas o intervalos asociados a cada sesión).

Importante: No te limites a explicar cómo desarrollar la aplicación. Quiero que escribas el código, crees los archivos, ejecutes las pruebas y pongas en funcionamiento WorkTrack en mi computadora, utilizando las herramientas y permisos disponibles.

Para comenzar: inspeccioná el entorno y presentame el plan de la Fase 1. No escribas código hasta que lo apruebe.
