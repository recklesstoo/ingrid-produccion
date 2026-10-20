# Ingrid Produccion

Ingesta y analisis de generacion y operacion de centrales EISA.

El flujo mensual recibe un ZIP, procesa Balance, SMEC y Operacion Diaria, corrige rollover, estima datos inconsistentes y genera salidas auditables.

## Ejecucion

```bash
python3 ingestores/ingrid_ingestar_mes.py --zip <archivo.zip> --year 2025 --month 12
```

No se versionan datos operativos, bases, ZIP ni credenciales.
