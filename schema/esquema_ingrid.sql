-- Modelo analitico de Ingrid: medicion, operacion, produccion y causas.
CREATE TABLE IF NOT EXISTS dim_planta (planta_id TEXT PRIMARY KEY, nombre TEXT NOT NULL, activo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS dim_unidad (
  unidad_id TEXT PRIMARY KEY, planta_id TEXT NOT NULL, nombre TEXT NOT NULL,
  potencia_mw REAL, tipo TEXT, activo INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY (planta_id) REFERENCES dim_planta(planta_id)
);
CREATE TABLE IF NOT EXISTS medicion_15min (
  planta_id TEXT NOT NULL, unidad_id TEXT, periodo TEXT NOT NULL, timestamp_utc TEXT NOT NULL,
  energia_bruta_mwh REAL, energia_neta_mwh REAL, consumo_mwh REAL, smec_mwh REAL,
  rollover_corregido INTEGER NOT NULL DEFAULT 0, fuente TEXT, calidad TEXT, metodo TEXT, motivo TEXT,
  PRIMARY KEY (planta_id, unidad_id, timestamp_utc)
);
CREATE TABLE IF NOT EXISTS operacion_horaria (
  planta_id TEXT NOT NULL, unidad_id TEXT NOT NULL, periodo TEXT NOT NULL, timestamp_utc TEXT NOT NULL,
  en_linea INTEGER, estado TEXT, capacidad_disponible_mw REAL, potencia_limitada_mw REAL,
  hon REAL, hol REAL, rsh REAL, hmp REAL, foh REAL, total_periodo REAL,
  fuente TEXT, calidad TEXT, motivo TEXT,
  PRIMARY KEY (planta_id, unidad_id, timestamp_utc)
);
CREATE TABLE IF NOT EXISTS causa_no_generacion (
  id INTEGER PRIMARY KEY AUTOINCREMENT, planta_id TEXT NOT NULL, unidad_id TEXT, periodo TEXT NOT NULL,
  inicio_utc TEXT NOT NULL, fin_utc TEXT, tipo TEXT NOT NULL CHECK(tipo IN ('evento','restriccion','limitacion')),
  origen TEXT NOT NULL CHECK(origen IN ('unidad','planta','CND','sistema')),
  codigo TEXT, descripcion TEXT, potencia_perdida_mw REAL, energia_perdida_mwh REAL,
  programado INTEGER, fuente TEXT, calidad TEXT
);
CREATE TABLE IF NOT EXISTS kpi_unidad_periodo (
  planta_id TEXT NOT NULL, unidad_id TEXT NOT NULL, periodo TEXT NOT NULL,
  generacion_mwh REAL, disponibilidad_pct REAL, efor_pct REAL, ea_pct REAL, por_pct REAL,
  foh_h REAL, efdh_h REAL, horas_servicio REAL, horas_reserva_frio REAL,
  perdida_evento_mwh REAL, perdida_restriccion_mwh REAL, perdida_limitacion_mwh REAL,
  perdida_fisica_mwh REAL, intervalos_estimados INTEGER, intervalos_hueco INTEGER,
  PRIMARY KEY (planta_id, unidad_id, periodo)
);
CREATE INDEX IF NOT EXISTS idx_medicion_periodo ON medicion_15min(periodo, planta_id);
CREATE INDEX IF NOT EXISTS idx_operacion_periodo ON operacion_horaria(periodo, planta_id, unidad_id);
CREATE INDEX IF NOT EXISTS idx_causa_periodo ON causa_no_generacion(periodo, tipo, planta_id);
