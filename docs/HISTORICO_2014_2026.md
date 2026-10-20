# Histórico operativo 2014-2026

## Regla de disponibilidad histórica

Montelirio (El Alto) operó antes que Pando. Pando se incorpora al histórico operativo a partir de 2019. Por tanto:

- La ausencia de Pando antes de 2019 no es un hueco de datos.
- Los KPI de Pando anteriores a 2019 deben quedar como `no_aplica`, no como cero ni como indisponible.
- Montelirio puede tener producción, operación, alarmas y datos hídricos en periodos donde Pando todavía no existía en el conjunto operativo.
- El consolidado corporativo debe indicar qué plantas estaban activas en cada periodo.

## Capas de ingesta

1. **Catálogo**: ruta, nombre, formato, tamaño, fechas detectadas y tipo probable.
2. **RAW**: archivo original conservado sin transformaciones.
3. **Perfilado**: hojas, columnas, fechas, unidades, duplicados y calidad.
4. **Canónico**: variables homologadas a una estructura común, manteniendo el campo original.
5. **Analítico**: generación, operación, hidrología, eventos, restricciones y KPI.

Los formatos y columnas pueden cambiar por año. La homologación debe usar un diccionario de variables versionado, nunca asumir que una columna con nombre parecido tiene la misma definición.

## Prioridad de fuentes

- SMEC es la fuente oficial de generación, salvo rollover o reinicio del contador.
- El rollover se corrige con delta validado y queda marcado en calidad.
- Operación diaria determina estado en línea y disponibilidad.
- SCADA/balance se conserva para pérdidas, consumo, hidráulica y diagnóstico.
- Restricción CND, limitación técnica y evento operativo son causas distintas.

## Ejecución del catálogo

Con el recurso SMB montado en GVFS:

```bash
python3 ingestores/catalogar_historico_smb.py \
  --location smb://172.16.30.200/operaciones/ \
  --output work/catalogo_historico_2014_2026.csv
```

El catálogo no copia ni modifica archivos del servidor. Las credenciales deben gestionarse fuera del repositorio.
