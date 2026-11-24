{{ config(indexes=[{'columns': ['project_key']}]) }}

-- Q7. Grain: one finding. Raw, unscaled values for Model A. USER rows stay out until the MODEL_TRAINING consent reaches the
-- warehouse (D-21, D-317h). risk_score and risk_class come from ml_outputs in P7 and are NULL until then (D-316b).
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
