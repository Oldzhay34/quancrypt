{{ config(indexes=[{'columns': ['project_key']}]) }}

-- Q1 to Q3 (docs/data/warehouse-design.md section 9). Grain: project x algorithm family x usage context x priority x
-- test code. A location (unit, file, line) counts once: user projects are scanned again and again and their findings carry
-- no scan id (D-317a); for findings without a file or line (user projects, 35% of the corpus) the count is a lower bound.
select
    p.project_key,
    p.origin,
    a.algorithm_family,
    a.quantum_status,
    u.usage_context,
    pr.priority,
    f.in_test_code,
    count(distinct concat_ws('|', f.unit_path, coalesce(f.file_path, ''), coalesce(f.line_start::text, ''))) as location_count,
    count(distinct case when f.hndl_exposure then concat_ws('|', f.unit_path, coalesce(f.file_path, ''), coalesce(f.line_start::text, '')) end) as hndl_location_count,
    count(*) as raw_finding_count
from {{ ref('fact_crypto_finding') }} f
join {{ ref('dim_project') }} p on p.project_sk = f.project_sk
join {{ ref('dim_algorithm') }} a on a.algorithm_sk = f.algorithm_sk
join {{ ref('dim_usage_context') }} u on u.usage_context_sk = f.usage_context_sk
join {{ ref('dim_priority') }} pr on pr.priority_sk = f.priority_sk
group by p.project_key, p.origin, a.algorithm_family, a.quantum_status, u.usage_context, pr.priority, f.in_test_code
