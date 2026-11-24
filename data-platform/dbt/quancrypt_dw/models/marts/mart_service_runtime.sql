{{ config(indexes=[{'columns': ['project_key']}]) }}

-- Q4. Grain: one service (the current row of dim_service); the version history is dim_service itself. A location is one
-- (unit, file, line, algorithm family, usage context) as in mart_inventory_summary (D-317a): two usages on the same
-- line (SHA1withRSA is a signature and a hash) are two locations.
select
    s.project_key,
    s.unit_path,
    s.java_version,
    s.java_major,
    s.spring_boot_version,
    count(distinct case when f.finding_id is not null then concat_ws('|', f.unit_path, coalesce(f.file_path, ''), coalesce(f.line_start::text, ''), a.algorithm_family, u.usage_context) end) as location_count,
    count(distinct case when a.quantum_status = 'VULNERABLE' then concat_ws('|', f.unit_path, coalesce(f.file_path, ''), coalesce(f.line_start::text, ''), a.algorithm_family, u.usage_context) end) as vulnerable_location_count,
    count(distinct case when f.hndl_exposure then concat_ws('|', f.unit_path, coalesce(f.file_path, ''), coalesce(f.line_start::text, ''), a.algorithm_family, u.usage_context) end) as hndl_location_count
from {{ ref('dim_service') }} s
left join {{ ref('fact_crypto_finding') }} f on f.service_sk = s.service_sk
left join {{ ref('dim_algorithm') }} a on a.algorithm_sk = f.algorithm_sk
left join {{ ref('dim_usage_context') }} u on u.usage_context_sk = f.usage_context_sk
where s.is_current
group by s.project_key, s.unit_path, s.java_version, s.java_major, s.spring_boot_version
