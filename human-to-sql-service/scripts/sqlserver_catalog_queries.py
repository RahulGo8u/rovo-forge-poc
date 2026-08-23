"""SQL Server 2017 catalog queries used by the offline extractor.

Every statement is a single SELECT/CTE and reads only sys catalog views.
"""
from __future__ import annotations

DATABASES_SQL = """
SELECT
  name,
  database_id,
  state_desc,
  compatibility_level,
  collation_name,
  is_read_only,
  containment_desc,
  recovery_model_desc,
  create_date,
  HAS_DBACCESS(name) AS has_access
FROM sys.databases
WHERE database_id > 4
ORDER BY name;
"""

SERVER_SQL = """
SELECT
  CAST(SERVERPROPERTY('ServerName') AS nvarchar(256)) AS server_name,
  CAST(SERVERPROPERTY('MachineName') AS nvarchar(256)) AS machine_name,
  CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS product_version,
  CAST(SERVERPROPERTY('ProductLevel') AS nvarchar(128)) AS product_level,
  CAST(SERVERPROPERTY('Edition') AS nvarchar(256)) AS edition,
  ORIGINAL_LOGIN() AS login_name,
  DB_NAME() AS database_name;
"""

QUERIES: dict[str, str] = {
    "schemas": """
SELECT
  schema_id,
  name,
  principal_id
FROM sys.schemas
WHERE name NOT IN ('sys', 'INFORMATION_SCHEMA')
ORDER BY name;
""",
    "objects": """
SELECT
  o.object_id,
  s.name AS schema_name,
  o.name AS object_name,
  o.type,
  o.type_desc,
  o.create_date,
  o.modify_date,
  o.parent_object_id,
  CAST(CASE WHEN t.object_id IS NULL THEN 0 ELSE 1 END AS bit) AS is_table,
  t.temporal_type,
  t.history_table_id,
  t.is_memory_optimized,
  t.is_external,
  t.is_node,
  t.is_edge,
  CAST(CASE WHEN v.object_id IS NULL THEN 0 ELSE 1 END AS bit) AS is_view,
  v.is_replicated AS view_is_replicated
FROM sys.objects AS o
INNER JOIN sys.schemas AS s ON s.schema_id = o.schema_id
LEFT JOIN sys.tables AS t ON t.object_id = o.object_id
LEFT JOIN sys.views AS v ON v.object_id = o.object_id
WHERE o.is_ms_shipped = 0
ORDER BY s.name, o.name, o.object_id;
""",
    "columns": """
SELECT
  c.object_id,
  s.name AS schema_name,
  o.name AS object_name,
  c.column_id,
  c.name AS column_name,
  TYPE_SCHEMA_NAME(c.user_type_id) AS type_schema,
  ty.name AS type_name,
  c.max_length,
  c.precision,
  c.scale,
  c.is_nullable,
  c.collation_name,
  c.is_identity,
  ic.seed_value AS identity_seed,
  ic.increment_value AS identity_increment,
  c.is_computed,
  cc.definition AS computed_definition,
  cc.is_persisted,
  c.is_rowguidcol,
  c.is_filestream,
  c.is_sparse,
  c.is_column_set,
  c.is_hidden,
  c.generated_always_type_desc,
  dc.name AS default_name,
  dc.definition AS default_definition,
  CAST(CASE WHEN c.encryption_type IS NULL THEN 0 ELSE 1 END AS bit) AS is_encrypted,
  c.encryption_type_desc,
  c.column_encryption_key_id
FROM sys.columns AS c
INNER JOIN sys.objects AS o ON o.object_id = c.object_id
INNER JOIN sys.schemas AS s ON s.schema_id = o.schema_id
INNER JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.identity_columns AS ic
  ON ic.object_id = c.object_id AND ic.column_id = c.column_id
LEFT JOIN sys.computed_columns AS cc
  ON cc.object_id = c.object_id AND cc.column_id = c.column_id
LEFT JOIN sys.default_constraints AS dc ON dc.object_id = c.default_object_id
WHERE o.is_ms_shipped = 0
ORDER BY s.name, o.name, c.column_id;
""",
    "constraints": """
SELECT
  'KEY' AS constraint_kind,
  kc.object_id AS constraint_object_id,
  kc.parent_object_id,
  s.name AS schema_name,
  o.name AS object_name,
  kc.name AS constraint_name,
  kc.type_desc,
  kc.unique_index_id AS backing_index_id,
  CAST(NULL AS nvarchar(max)) AS definition,
  CAST(0 AS bit) AS is_disabled,
  CAST(0 AS bit) AS is_not_trusted,
  CAST(NULL AS nvarchar(60)) AS delete_action,
  CAST(NULL AS nvarchar(60)) AS update_action
FROM sys.key_constraints AS kc
INNER JOIN sys.objects AS o ON o.object_id = kc.parent_object_id
INNER JOIN sys.schemas AS s ON s.schema_id = o.schema_id
UNION ALL
SELECT
  'FOREIGN_KEY',
  fk.object_id,
  fk.parent_object_id,
  s.name,
  o.name,
  fk.name,
  fk.type_desc,
  NULL,
  NULL,
  fk.is_disabled,
  fk.is_not_trusted,
  fk.delete_referential_action_desc,
  fk.update_referential_action_desc
FROM sys.foreign_keys AS fk
INNER JOIN sys.objects AS o ON o.object_id = fk.parent_object_id
INNER JOIN sys.schemas AS s ON s.schema_id = o.schema_id
UNION ALL
SELECT
  'CHECK',
  cc.object_id,
  cc.parent_object_id,
  s.name,
  o.name,
  cc.name,
  cc.type_desc,
  NULL,
  cc.definition,
  cc.is_disabled,
  cc.is_not_trusted,
  NULL,
  NULL
FROM sys.check_constraints AS cc
INNER JOIN sys.objects AS o ON o.object_id = cc.parent_object_id
INNER JOIN sys.schemas AS s ON s.schema_id = o.schema_id
ORDER BY schema_name, object_name, constraint_kind, constraint_name;
""",
    "foreign_keys": """
SELECT
  fk.object_id AS foreign_key_id,
  fk.name AS foreign_key_name,
  ps.name AS parent_schema,
  pt.name AS parent_table,
  pc.name AS parent_column,
  rs.name AS referenced_schema,
  rt.name AS referenced_table,
  rc.name AS referenced_column,
  fkc.constraint_column_id AS ordinal,
  fk.delete_referential_action_desc AS delete_action,
  fk.update_referential_action_desc AS update_action,
  fk.is_disabled,
  fk.is_not_trusted
FROM sys.foreign_key_columns AS fkc
INNER JOIN sys.foreign_keys AS fk ON fk.object_id = fkc.constraint_object_id
INNER JOIN sys.tables AS pt ON pt.object_id = fkc.parent_object_id
INNER JOIN sys.schemas AS ps ON ps.schema_id = pt.schema_id
INNER JOIN sys.columns AS pc
  ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
INNER JOIN sys.tables AS rt ON rt.object_id = fkc.referenced_object_id
INNER JOIN sys.schemas AS rs ON rs.schema_id = rt.schema_id
INNER JOIN sys.columns AS rc
  ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
ORDER BY ps.name, pt.name, fk.name, fkc.constraint_column_id;
""",
    "indexes": """
SELECT
  i.object_id,
  s.name AS schema_name,
  o.name AS object_name,
  i.index_id,
  i.name AS index_name,
  i.type,
  i.type_desc,
  i.is_unique,
  i.is_primary_key,
  i.is_unique_constraint,
  i.has_filter,
  i.filter_definition,
  i.is_disabled,
  i.fill_factor,
  i.allow_row_locks,
  i.allow_page_locks,
  ic.index_column_id,
  ic.key_ordinal,
  ic.is_descending_key,
  ic.is_included_column,
  c.column_id,
  c.name AS column_name
FROM sys.indexes AS i
INNER JOIN sys.objects AS o ON o.object_id = i.object_id
INNER JOIN sys.schemas AS s ON s.schema_id = o.schema_id
LEFT JOIN sys.index_columns AS ic
  ON ic.object_id = i.object_id AND ic.index_id = i.index_id
LEFT JOIN sys.columns AS c
  ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE o.is_ms_shipped = 0
  AND i.index_id > 0
  AND i.is_hypothetical = 0
ORDER BY s.name, o.name, i.index_id, ic.index_column_id;
""",
    "modules": """
SELECT
  o.object_id,
  s.name AS schema_name,
  o.name AS object_name,
  o.type,
  o.type_desc,
  o.create_date,
  o.modify_date,
  m.definition,
  m.uses_ansi_nulls,
  m.uses_quoted_identifier,
  m.is_schema_bound,
  m.uses_database_collation,
  m.is_recompiled,
  m.null_on_null_input,
  m.execute_as_principal_id,
  CAST(CASE WHEN m.definition IS NULL THEN 0 ELSE 1 END AS bit) AS definition_visible
FROM sys.objects AS o
INNER JOIN sys.schemas AS s ON s.schema_id = o.schema_id
LEFT JOIN sys.sql_modules AS m ON m.object_id = o.object_id
WHERE o.is_ms_shipped = 0
  AND o.type IN ('V','P','PC','FN','IF','TF','FS','FT','TR')
ORDER BY s.name, o.name;
""",
    "parameters": """
SELECT
  p.object_id,
  s.name AS schema_name,
  o.name AS object_name,
  p.parameter_id,
  p.name AS parameter_name,
  TYPE_SCHEMA_NAME(p.user_type_id) AS type_schema,
  ty.name AS type_name,
  p.max_length,
  p.precision,
  p.scale,
  p.is_output,
  p.has_default_value,
  CONVERT(nvarchar(max), p.default_value) AS default_value,
  p.is_readonly,
  p.is_nullable
FROM sys.parameters AS p
INNER JOIN sys.objects AS o ON o.object_id = p.object_id
INNER JOIN sys.schemas AS s ON s.schema_id = o.schema_id
INNER JOIN sys.types AS ty ON ty.user_type_id = p.user_type_id
WHERE o.is_ms_shipped = 0
ORDER BY s.name, o.name, p.parameter_id;
""",
    "dependencies": """
SELECT
  d.referencing_id,
  rs.name AS referencing_schema,
  ro.name AS referencing_object,
  ro.type AS referencing_type,
  d.referencing_minor_id,
  d.referenced_server_name,
  d.referenced_database_name,
  d.referenced_schema_name,
  d.referenced_entity_name,
  d.referenced_minor_name,
  d.referenced_id,
  ref_o.type AS referenced_type,
  d.referenced_minor_id,
  d.is_schema_bound_reference,
  d.is_caller_dependent,
  d.is_ambiguous
FROM sys.sql_expression_dependencies AS d
INNER JOIN sys.objects AS ro ON ro.object_id = d.referencing_id
INNER JOIN sys.schemas AS rs ON rs.schema_id = ro.schema_id
LEFT JOIN sys.objects AS ref_o ON ref_o.object_id = d.referenced_id
WHERE ro.is_ms_shipped = 0
ORDER BY rs.name, ro.name, d.referenced_database_name, d.referenced_schema_name, d.referenced_entity_name;
""",
    "synonyms": """
SELECT
  sy.object_id,
  s.name AS schema_name,
  sy.name AS synonym_name,
  sy.base_object_name,
  sy.create_date,
  sy.modify_date
FROM sys.synonyms AS sy
INNER JOIN sys.schemas AS s ON s.schema_id = sy.schema_id
ORDER BY s.name, sy.name;
""",
    "triggers": """
SELECT
  tr.object_id,
  s.name AS schema_name,
  tr.name AS trigger_name,
  tr.parent_id,
  OBJECT_SCHEMA_NAME(tr.parent_id) AS parent_schema,
  OBJECT_NAME(tr.parent_id) AS parent_object,
  tr.parent_class_desc,
  tr.is_instead_of_trigger,
  tr.is_disabled,
  tr.create_date,
  tr.modify_date,
  te.type_desc AS event_type,
  m.definition
FROM sys.triggers AS tr
LEFT JOIN sys.objects AS parent_o ON parent_o.object_id = tr.parent_id
LEFT JOIN sys.schemas AS s ON s.schema_id = parent_o.schema_id
LEFT JOIN sys.trigger_events AS te ON te.object_id = tr.object_id
LEFT JOIN sys.sql_modules AS m ON m.object_id = tr.object_id
WHERE tr.is_ms_shipped = 0
ORDER BY s.name, parent_object, tr.name, te.type_desc;
""",
    "sequences": """
SELECT
  seq.object_id,
  s.name AS schema_name,
  seq.name AS sequence_name,
  TYPE_SCHEMA_NAME(seq.user_type_id) AS type_schema,
  ty.name AS type_name,
  seq.start_value,
  seq.increment,
  seq.minimum_value,
  seq.maximum_value,
  seq.is_cycling,
  seq.is_cached,
  seq.cache_size
FROM sys.sequences AS seq
INNER JOIN sys.schemas AS s ON s.schema_id = seq.schema_id
INNER JOIN sys.types AS ty ON ty.user_type_id = seq.user_type_id
ORDER BY s.name, seq.name;
""",
    "extended_properties": """
SELECT
  ep.class,
  ep.class_desc,
  ep.major_id,
  ep.minor_id,
  ep.name AS property_name,
  CONVERT(nvarchar(max), ep.value) AS property_value,
  CASE
    WHEN ep.class = 0 THEN DB_NAME()
    WHEN ep.class = 1 THEN OBJECT_SCHEMA_NAME(ep.major_id)
    WHEN ep.class = 3 THEN SCHEMA_NAME(ep.major_id)
    ELSE NULL
  END AS schema_name,
  CASE WHEN ep.class = 1 THEN OBJECT_NAME(ep.major_id) ELSE NULL END AS object_name,
  CASE
    WHEN ep.class = 1 AND ep.minor_id > 0
    THEN COL_NAME(ep.major_id, ep.minor_id)
    ELSE NULL
  END AS column_name
FROM sys.extended_properties AS ep
ORDER BY ep.class, ep.major_id, ep.minor_id, ep.name;
""",
}

RESULT_SET_SQL = """
SELECT
  requested.object_id,
  described.column_ordinal,
  described.name AS column_name,
  described.is_nullable,
  described.system_type_id,
  described.system_type_name,
  described.max_length,
  described.precision,
  described.scale,
  described.collation_name,
  described.user_type_database,
  described.user_type_schema,
  described.user_type_name,
  described.source_server,
  described.source_database,
  described.source_schema,
  described.source_table,
  described.source_column,
  described.is_identity_column,
  described.is_part_of_unique_key,
  described.is_updateable,
  described.error_number,
  described.error_severity,
  described.error_state,
  described.error_message,
  described.error_type,
  described.error_type_desc
FROM (SELECT CAST(? AS int) AS object_id) AS requested
CROSS APPLY sys.dm_exec_describe_first_result_set_for_object(requested.object_id, 1) AS described
ORDER BY described.column_ordinal;
"""
