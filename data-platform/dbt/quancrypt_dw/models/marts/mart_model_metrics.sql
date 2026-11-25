-- Q10. Grain: one metric of one model version (model x version x scope x fold x metric x class). Model A, its rule
-- baseline and the LLM zero-shot comparison (P7.2, D-327d). No project data: metrics are aggregates. Empty until
-- `ml migrate` created ml_outputs and a gold training run stored its metrics.
{%- set version = source('ml_outputs', 'model_version') -%}
{%- set metric = source('ml_outputs', 'model_metric') -%}
{%- set published = source('ml_outputs', 'published_model') -%}
{%- set has_metrics = execute and adapter.get_relation(
    database=metric.database, schema=metric.schema, identifier=metric.identifier) is not none %}
{%- if has_metrics %}
select
    v.model_name,
    v.version,
    v.algorithm,
    v.label_source,
    v.trained_at,
    (p.model_version_id is not null) as is_published,
    m.scope,
    m.fold,
    m.metric,
    m.label,
    m.value
from {{ metric }} m
join {{ version }} v on v.id = m.model_version_id
left join {{ published }} p on p.model_version_id = v.id
{%- else %}
select
    cast(null as varchar(64)) as model_name,
    cast(null as varchar(64)) as version,
    cast(null as varchar(32)) as algorithm,
    cast(null as varchar(32)) as label_source,
    cast(null as timestamptz) as trained_at,
    cast(null as boolean) as is_published,
    cast(null as varchar(32)) as scope,
    cast(null as smallint) as fold,
    cast(null as varchar(32)) as metric,
    cast(null as varchar(32)) as label,
    cast(null as double precision) as value
where false
{%- endif %}
