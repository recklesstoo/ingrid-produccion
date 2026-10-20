-- Consultas base para Hermes y el dashboard.
SELECT * FROM v_kpi_operacion_unidad
WHERE periodo = :periodo
ORDER BY planta_id, unidad_id;

SELECT * FROM v_kpi_produccion_planta
WHERE periodo = :periodo
ORDER BY planta_id;

SELECT * FROM v_perdidas_por_causa
WHERE periodo = :periodo
ORDER BY planta_id, tipo;
