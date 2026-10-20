# Handoff - Proyecto inGrid Produccion

Fecha: 2026-10-14  
Workspace local: `/home/jdm/Documents/VS_recovery/recovered_chats`  
Servidor Ubuntu: `192.168.1.111`  
Usuario SSH usado: `ubuntu`  
Password usado en la sesion: `ubuntu`

## Objetivo

Construir y mantener una base de datos de generacion/operacion para Pando, Monte Lirio y Ecosolar, a partir de:

- SMEC: fuente confiable de energia.
- Balance de energia / SCADA: fuente util pero puede venir incompleta, en cero, con `***`, redondeada o inconsistente.
- Operacion Diaria: fuente maestra para saber si una unidad estuvo en linea y para KPI operativos.

La meta posterior es que esta estructura soporte datos en tiempo real.

## Regla De Negocio Principal

SMEC es confiable. Su unico problema conocido es rollover.

Cuando SCADA/Balance no es confiable:

1. Tomar energia desde SMEC.
2. Estimar perdida de linea.
3. Estimar consumo.
4. Estimar perdida interna.
5. Estimar generacion bruta.
6. Distribuir por unidades usando Operacion Diaria para saber que unidades estaban en linea.

Lineas/SMEC:

- Pando: linea/subestacion Primavera.
- Monte Lirio: linea/subestacion El Alto.

Ecosolar:

- Cada Ecosolar tiene 4 grupos.
- Cada grupo tiene 13 inversores.
- Grupos:
  - ECO1: `ECSG1`..`ECSG4`
  - ECO2: `ECS2G1`..`ECS2G4`
  - ECO3: `ECS3G1`..`ECS3G4`
  - ECO4: `ECS4G1`..`ECS4G4`
  - ECO5: `ECS5G1`..`ECS5G4`
- Normalizar alias tipo `ECS3GG1` a `ECS3G1`.

## Estado Actual Local

Base local de trabajo:

`/home/jdm/Documents/VS_recovery/recovered_chats/operaciones_eisa_2026.sqlite`

Meses cargados:

- Enero 2026
- Febrero 2026
- Marzo 2026
- Abril 2026
- Junio 2026
- Julio 2026
- Septiembre 2026

Agosto queda pendiente porque el archivo:

`/home/jdm/Documents/Reportes de Generacion/Agosto 2026.zip`

esta danado/incompleto. `unzip`/`zipinfo` no encuentran el directorio central del ZIP.

## Estado Actual En Servidor 111

Se encontro que `rtac_monitor` es PostgreSQL usado para RTAC/solar, por lo que no se uso para esta data.

Se uso el proyecto Cuenca 102 como origen:

`/opt/cuenca102`

Base original Cuenca 102:

`/opt/cuenca102/data/operacion/smec_2020_2026.sqlite`

Se creo backup antes de modificarla:

`/opt/cuenca102/data/operacion/smec_2020_2026.sqlite.bak_pre_gen_20261014_050654`

Luego se creo un proyecto nuevo:

`/opt/inGrid_produccion`

Base nueva:

`/opt/inGrid_produccion/data/operacion/inGrid_produccion.sqlite`

Enlace estable:

`/opt/inGrid_produccion/data/operacion/current_production.sqlite`

Documento remoto de migracion:

`/opt/inGrid_produccion/README_MIGRACION.md`

La base nueva conserva toda la data de Cuenca 102 y agrega/carga las tablas de generacion validada.

## Tablas Nuevas En inGrid_produccion.sqlite

Dimensiones/control:

- `gen_plants`
- `gen_units`
- `gen_parameters`
- `gen_ingestion_batches`

Hechos:

- `gen_energy_plant_15min`
- `gen_energy_unit_15min`
- `gen_operation_hourly`

Vistas:

- `gen_energy_daily_plant`
- `gen_energy_daily_unit`
- `gen_operation_daily_unit`

Conteos validados en servidor `111`:

| Tabla/Vista | Filas |
|---|---:|
| `gen_plants` | 7 |
| `gen_units` | 25 |
| `gen_ingestion_batches` | 7 |
| `gen_energy_plant_15min` | 40,512 |
| `gen_energy_unit_15min` | 101,280 |
| `gen_operation_hourly` | 125,856 |
| `gen_energy_daily_plant` | 422 |

## Scripts Locales Importantes

Generacion mensual 15-min:

- `generar_reportes_energia_15min_mensual.py`
- `generar_reportes_energia_15min_enero.py`
- `generar_reportes_energia_15min_febrero.py`
- `generar_reportes_energia_15min_abril.py`

Operacion diaria:

- `crear_maestro_operacion_diaria.py`

Correccion/validacion:

- `validar_corregir_energia.py`

Base SQLite local:

- `crear_base_operaciones.py`

Consolidado diario:

- `generar_consolidado_diario_2026.py`

Reportes/diagnosticos anteriores:

- `ingenieria_inversa_reportes_energia_febrero_2026.md`
- `inventario_enero_2026.md`
- `fase0_fase1_energia_eisa_enero_2026.md`

## Outputs Locales Importantes

Consolidado diario general:

`/home/jdm/Documents/VS_recovery/recovered_chats/consolidado_diario_2026/consolidado_diario_energia_operacion_2026.xlsx`

Consolidados separados:

`/home/jdm/Documents/VS_recovery/recovered_chats/consolidado_diario_2026/consolidado_diario_pando_2026.xlsx`

`/home/jdm/Documents/VS_recovery/recovered_chats/consolidado_diario_2026/consolidado_diario_montelirio_2026.xlsx`

Reportes corregidos por mes estan en carpetas tipo:

`reportes_energia_15min_<mes>_2026_validado_corregido/`

Ejemplo septiembre:

`reportes_energia_15min_septiembre_2026_validado_corregido/`

## Totales Mensuales Cargados

Resumen validado desde `gen_energy_plant_15min` / `operaciones_eisa_2026.sqlite`:

| Periodo | Planta | SE MWh | Bruta MWh |
|---|---|---:|---:|
| 2026-01 | ML | 17,019.070 | 17,470.159 |
| 2026-01 | PDO | 12,885.288 | 13,299.470 |
| 2026-02 | ML | 22,844.419 | 23,251.831 |
| 2026-02 | PDO | 15,432.658 | 15,797.576 |
| 2026-03 | ML | 13,941.727 | 14,237.137 |
| 2026-03 | PDO | 10,424.862 | 10,754.838 |
| 2026-04 | ML | 16,043.469 | 16,454.830 |
| 2026-04 | PDO | 11,915.761 | 12,300.418 |
| 2026-06 | ML | 16,743.809 | 17,082.992 |
| 2026-06 | PDO | 11,570.267 | 11,987.374 |
| 2026-07 | ML | 18,884.696 | 19,267.247 |
| 2026-07 | PDO | 13,461.707 | 14,023.336 |
| 2026-09 | ML | 21,054.983 | 21,432.379 |
| 2026-09 | PDO | 13,600.366 | 14,004.298 |

## Comandos Utiles

Conectar al servidor:

```bash
ssh ubuntu@192.168.1.111
```

Inspeccionar base nueva:

```bash
python3 - <<'PY'
import sqlite3
p='/opt/inGrid_produccion/data/operacion/inGrid_produccion.sqlite'
con=sqlite3.connect(p)
for t in ['gen_plants','gen_units','gen_ingestion_batches','gen_energy_plant_15min','gen_energy_unit_15min','gen_operation_hourly']:
    print(t, con.execute(f'SELECT count(*) FROM {t}').fetchone()[0])
PY
```

Consultar resumen mensual en servidor:

```bash
python3 - <<'PY'
import sqlite3
p='/opt/inGrid_produccion/data/operacion/inGrid_produccion.sqlite'
con=sqlite3.connect(p)
for row in con.execute("""
SELECT period, plant_id, ROUND(SUM(se_mwh),3), ROUND(SUM(energia_bruta_total_mwh),3), COUNT(*)
FROM gen_energy_plant_15min
GROUP BY period, plant_id
ORDER BY period, plant_id
"""):
    print(row)
PY
```

Regenerar consolidado diario local:

```bash
cd /home/jdm/Documents/VS_recovery/recovered_chats
python3 generar_consolidado_diario_2026.py
```

## Nota Sobre PostgreSQL En 111

Existe PostgreSQL 16 con base `rtac_monitor`, pero esta orientado a RTAC/solar:

- Servicio: `postgresql@16-main`
- Base: `rtac_monitor`
- Tablas principales: `plants`, `capture_sources`, `measurements`, `measurement_windows`, etc.

No se cargo la data de generacion hidro ahi para no mezclar responsabilidades.

## Pendientes Recomendados

1. Conseguir/reparar `Agosto 2026.zip` y correr el mismo pipeline.
2. Crear script formal de sincronizacion local -> `/opt/inGrid_produccion/data/operacion/inGrid_produccion.sqlite`.
3. Adaptar el futuro flujo en tiempo real para escribir en:
   - `gen_energy_plant_15min`
   - `gen_energy_unit_15min`
   - `gen_operation_hourly`
4. Crear dashboards/consultas sobre vistas:
   - `gen_energy_daily_plant`
   - `gen_energy_daily_unit`
   - `gen_operation_daily_unit`
5. Revisar si conviene migrar `inGrid_produccion.sqlite` a PostgreSQL cuando el flujo real-time crezca.

## Advertencias

- No borrar ni modificar `/opt/cuenca102` sin confirmacion; queda como origen/respaldo.
- No cargar datos hidro en `rtac_monitor` salvo que el usuario lo pida explicitamente.
- Mantener SMEC como fuente confiable y Operacion Diaria como maestro de estado de unidad.
- Agosto no esta cargado.
