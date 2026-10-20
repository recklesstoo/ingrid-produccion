# Dashboard KPI de Operacion

La plantilla de referencia se implementa con tres filtros:

- Central: Pando, Montelirio, Ecosolar y futuras plantas.
- Unidad: unidad o grupo generador.
- Periodo: mes operativo.

## Contrato de datos

La vista `kpi_unidad_periodo` debe entregar:

```text
periodo, planta_id, unidad_id
hon, hol, rsh, hmp, foh
sh, ah, ph, efdh
disponibilidad_propia_pct
disponibilidad_equivalente_pct
efor_pct, ea_pct, por_pct
generacion_mwh
perdida_evento_mwh
perdida_restriccion_mwh
perdida_limitacion_mwh
perdida_fisica_mwh
intervalos_estimados, intervalos_hueco
calidad, notas_calidad
```

## Reglas visuales

- Las perdidas por evento, restriccion y limitacion se muestran separadas.
- La calidad del dato siempre es visible.
- Un KPI no se presenta como definitivo si tiene huecos o fuentes conflictivas.
- El detalle de unidad debe poder compararse contra el total de planta.

La fuente original se mantiene fuera del repositorio; este directorio contiene solo el contrato conceptual y los componentes del dashboard.
