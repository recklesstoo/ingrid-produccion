CREATE VIEW IF NOT EXISTS v_kpi_operacion_unidad AS
SELECT
  o.planta_id, o.unidad_id, o.periodo,
  SUM(o.hon) AS hon, SUM(o.hol) AS hol, SUM(o.rsh) AS rsh,
  SUM(o.hmp) AS hmp, SUM(o.foh) AS foh,
  SUM(o.hon + o.rsh) AS horas_disponibles,
  SUM(o.total_periodo) AS horas_periodo,
  CASE WHEN SUM(o.total_periodo) > 0
       THEN 100.0 * SUM(o.hon + o.rsh) / SUM(o.total_periodo) END AS disponibilidad_pct,
  CASE WHEN SUM(o.total_periodo) > 0
       THEN 100.0 * SUM(o.foh) / SUM(o.total_periodo) END AS foh_pct,
  COUNT(*) AS registros,
  SUM(CASE WHEN o.calidad LIKE '%estim%' THEN 1 ELSE 0 END) AS registros_estimados
FROM operacion_horaria o
GROUP BY o.planta_id, o.unidad_id, o.periodo;

CREATE VIEW IF NOT EXISTS v_kpi_produccion_planta AS
SELECT
  planta_id, periodo,
  SUM(gross_total) AS generacion_bruta_mwh,
  SUM(net_total) AS generacion_neta_mwh,
  SUM(consumption) AS consumo_mwh,
  SUM(smec) AS smec_mwh,
  SUM(internal_loss) AS perdida_interna_mwh,
  SUM(line_loss) AS perdida_linea_mwh,
  SUM(total_loss) AS perdida_fisica_mwh,
  SUM(CASE WHEN quality LIKE '%estim%' THEN 1 ELSE 0 END) AS intervalos_estimados,
  SUM(CASE WHEN quality = 'hueco' THEN 1 ELSE 0 END) AS intervalos_hueco
FROM medicion_15min
GROUP BY planta_id, periodo;

CREATE VIEW IF NOT EXISTS v_perdidas_por_causa AS
SELECT planta_id, unidad_id, periodo, tipo, origen,
       SUM(energia_perdida_mwh) AS energia_perdida_mwh,
       COUNT(*) AS eventos
FROM causa_no_generacion
GROUP BY planta_id, unidad_id, periodo, tipo, origen;
