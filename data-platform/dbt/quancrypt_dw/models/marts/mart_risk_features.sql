{{ config(indexes=[{'columns': ['project_key']}]) }}

-- Q7. Grain: one finding. Raw, unscaled values for Model A. USER rows stay out until the MODEL_TRAINING consent reaches the
-- warehouse (D-21, D-317h). risk_score and risk_class come from ml_outputs in P7 and are NULL until then (D-316b).
-- gold_label (P7.1, D-322d, D-324d): the user's resolution of a disagreement, else the first labeller's label when the
-- second labeller agrees or did not label the record; an unresolved disagreement has none. It comes from the latest batch
-- with a final label; NULL until the labels schema exists (`ml migrate`) and the finding is labelled.
-- silver_label: the start rule table of crypto-domain section 1 (labelling guideline). The warehouse has no link-to-finding
-- table (D-310b), so rule 2's "on an inter-service path" is read as "a TLS key exchange" (TLS is a network connection by
-- definition); other P1 usages (RSA encryption, key wrapping, key agreement) fall to rule 3. Unresolved priority: NULL.
{%- set label_item = source('labels', 'label_batch_item') -%}
{%- set label_batch = source('labels', 'label_batch') -%}
{%- set label_gold = source('labels', 'gold_label') -%}
{%- set label_resolution = source('labels', 'label_resolution') -%}
{%- set has_labels = execute and adapter.get_relation(
    database=label_item.database, schema=label_item.schema, identifier=label_item.identifier) is not none %}
with features as (
    select
        f.finding_id,
        p.project_key,
        p.origin,
        p.is_outlier_project,
        a.algorithm_family,
        a.quantum_status,
        u.usage_context,
        l.location_kind,
        pr.priority,
        f.key_size_bits,
        f.key_size_known,
        f.mode,
        f.padding,
        f.hash,
        lib.library,
        f.confidence,
        f.in_test_code,
        f.hndl_exposure,
        s.java_major,
        s.spring_boot_version,
        count(*) over (partition by f.project_key) as project_finding_count,
        cast(null as numeric(5, 4)) as risk_score,
        cast(null as varchar(16)) as risk_class
    from {{ ref('fact_crypto_finding') }} f
    join {{ ref('dim_project') }} p on p.project_sk = f.project_sk
    join {{ ref('dim_service') }} s on s.service_sk = f.service_sk
    join {{ ref('dim_algorithm') }} a on a.algorithm_sk = f.algorithm_sk
    join {{ ref('dim_usage_context') }} u on u.usage_context_sk = f.usage_context_sk
    join {{ ref('dim_location_kind') }} l on l.location_kind_sk = f.location_kind_sk
    join {{ ref('dim_priority') }} pr on pr.priority_sk = f.priority_sk
    join {{ ref('dim_library') }} lib on lib.library_sk = f.library_sk
    where p.origin in ('CORPUS', 'BENCHMARK')
),

gold as (
{%- if has_labels %}
    select finding_id, gold_label
    from (
        select
            finding_id,
            gold_label,
            row_number() over (partition by finding_id order by created_at desc, batch_id desc) as recency
        from (
            select
                i.finding_id,
                i.batch_id,
                b.created_at,
                case
                    when r.risk_class is not null then r.risk_class
                    -- An unresolved disagreement has no gold label yet (D-324d).
                    when s.risk_class is not null and s.risk_class <> g.risk_class then null
                    else g.risk_class
                end as gold_label
            from {{ label_item }} i
            join {{ label_batch }} b on b.id = i.batch_id
            left join {{ label_gold }} g
                on g.batch_id = i.batch_id and g.finding_id = i.finding_id and g.labeler_role = 'FIRST'
            left join {{ label_gold }} s
                on s.batch_id = i.batch_id and s.finding_id = i.finding_id and s.labeler_role = 'SECOND'
            left join {{ label_resolution }} r on r.batch_id = i.batch_id and r.finding_id = i.finding_id
        ) labelled
        where gold_label is not null
    ) ranked
    where recency = 1
{%- else %}
    select cast(null as uuid) as finding_id, cast(null as varchar(16)) as gold_label
    where false
{%- endif %}
),

silver as (
    select
        finding_id,
        case
            when priority = 'P0' then 'CRITICAL'
            when priority = 'P1' and usage_context = 'TLS_KEY_EXCHANGE' then 'HIGH'
            when priority in ('P1', 'P2') then 'MEDIUM'
            when priority = 'P3' then 'LOW'
        end as rule_class,
        in_test_code
    from features
)

select
    f.*,
    cast(g.gold_label as varchar(16)) as gold_label,
    cast(
        case
            when not s.in_test_code then s.rule_class
            when s.rule_class = 'CRITICAL' then 'HIGH'
            when s.rule_class = 'HIGH' then 'MEDIUM'
            when s.rule_class is not null then 'LOW'
        end as varchar(16)
    ) as silver_label
from features f
join silver s on s.finding_id = f.finding_id
left join gold g on g.finding_id = f.finding_id
