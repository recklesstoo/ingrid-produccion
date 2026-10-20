# Estructura operacional

El flujo operacional de Ingrid se divide en:

```text
fuentes -> ingesta -> validacion -> modelo analitico -> KPI -> dashboard/Hermes
```

## Fuentes

- Operacion Diaria: estado y disponibilidad de unidades.
- SMEC: energia neta confiable y rollover.
- Balance/SCADA: energia auxiliar y señales de planta, sujeto a validacion.
- Eventos: disparos, fallas y salidas.
- Restricciones: instrucciones del CND o del sistema.
- Limitaciones: reducciones por condiciones propias de planta/unidad.

## Regla de clasificación

Una reducción ordenada por el CND es `restriccion`; una reducción por condición técnica propia es `limitacion`; una salida o falla puntual es `evento`.
