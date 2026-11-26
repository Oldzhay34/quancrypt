{{ config(indexes=[{'columns': ['project_key']}]) }}

-- Q6 (P7.4, D-337, D-338a). Grain: one corpus project with at least one finding outside test code. The raw crypto profile
-- (shares of algorithm families and usage contexts, findings per analysed unit) is the one source of the mining features;
-- the priority shares are read by the mining report only. USER and BENCHMARK projects stay out (D-337a). The labels come
-- from the last mining run (ml_outputs, ml/migrations 0004); NULL until `ml mine` ran or for a project it did not see.
{%- set families = dbt_utils.get_column_values(
    table=ref('dim_algorithm'), column='algorithm_family', order_by='algorithm_family', default=[]) %}
{%- set contexts = dbt_utils.get_column_values(
    table=ref('dim_usage_context'), column='usage_context', order_by='usage_context', default=[]) %}
{%- set assigned = source('ml_outputs', 'project_archetype') -%}
{%- set archetype = source('ml_outputs', 'archetype') -%}
{%- set mining_run = source('ml_outputs', 'mining_run') -%}
{%- set anomaly = source('ml_outputs', 'anomaly') -%}
{%- set has_mining = execute and adapter.get_relation(
    database=assigned.database, schema=assigned.schema, identifier=assigned.identifier) is not none %}
with findings as (
    select project_key, algorithm_family, usage_context, priority
    from {{ ref('mart_risk_features') }}
    where origin = 'CORPUS' and not in_test_code
),

units as (
    select project_key, count(*) as analysis_unit_count
    from {{ ref('dim_service') }}
    where is_current
    group by project_key
),

profile as (
    select
        f.project_key,
        u.analysis_unit_count,
        count(*) as finding_count,
        count(*)::double precision / u.analysis_unit_count as findings_per_unit
{%- for family in families %},
        avg((f.algorithm_family = '{{ family }}')::int)::double precision as share_alg_{{ family | lower }}
{%- endfor %}
{%- for context in contexts if context != '~UNRESOLVED' %},
        avg((f.usage_context = '{{ context }}')::int)::double precision as share_ctx_{{ context | lower }}
{%- endfor %}
{%- for priority in ['P0', 'P1', 'P2', 'P3'] %},
        avg((f.priority = '{{ priority }}')::int)::double precision as share_{{ priority | lower }}
{%- endfor %}
    from findings f
    join units u on u.project_key = f.project_key
    group by f.project_key, u.analysis_unit_count
),

labels as (
{%- if has_mining %}
    select
        p.project_key,
        k.cluster_no as archetype_no,
        k.name as archetype_name,
        h.cluster_no as hdbscan_cluster_no,
        x.score as anomaly_score,
        x.is_flagged as is_anomaly,
        (select max(run_at) from {{ mining_run }}) as mined_at
    from profile p
    left join (
        select a.project_key, a.cluster_no, c.name
        from {{ assigned }} a
        join {{ archetype }} c on c.technique = a.technique and c.cluster_no = a.cluster_no
        where a.technique = 'KMEANS'
    ) k on k.project_key = p.project_key
    left join {{ assigned }} h on h.project_key = p.project_key and h.technique = 'HDBSCAN'
    left join {{ anomaly }} x on x.project_key = p.project_key and x.technique = 'ISOLATION_FOREST'
{%- else %}
    select
        cast(null as char(64)) as project_key,
        cast(null as smallint) as archetype_no,
        cast(null as varchar(128)) as archetype_name,
        cast(null as smallint) as hdbscan_cluster_no,
        cast(null as double precision) as anomaly_score,
        cast(null as boolean) as is_anomaly,
        cast(null as timestamptz) as mined_at
    where false
{%- endif %}
)

select
    p.*,
    cast('CORPUS' as varchar(16)) as origin,
    l.archetype_no,
    l.archetype_name,
    l.hdbscan_cluster_no,
    l.anomaly_score,
    l.is_anomaly,
    l.mined_at
from profile p
left join labels l on l.project_key = p.project_key
