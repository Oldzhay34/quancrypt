{{ config(indexes=[{'columns': ['date_key']}, {'columns': ['project_sk']}, {'columns': ['service_sk']}, {'columns': ['algorithm_sk']}, {'columns': ['usage_context_sk']}, {'columns': ['location_kind_sk']}, {'columns': ['priority_sk']}, {'columns': ['library_sk']}, {'columns': ['source_sk']}, {'columns': ['project_key']}]) }}

-- Grain: one crypto usage reported by one source event, one prep.finding row (D-317a). Each row is bound to the current
-- row of its project and service (SCD2 is dimension history only, D-317d).
select
    f.finding_id,
    {{ date_key('u.analysed_at') }} as date_key,
    p.project_sk,
    s.service_sk,
    {{ sk(['f.algorithm_family']) }} as algorithm_sk,
    {{ sk(['f.usage_context']) }} as usage_context_sk,
    {{ sk(['f.location_kind']) }} as location_kind_sk,
    {{ sk(['f.priority']) }} as priority_sk,
    {{ sk(["coalesce(f.library, '~UNRESOLVED')"]) }} as library_sk,
    {{ sk(['p.origin']) }} as source_sk,
    f.project_key,
    f.source_event_id,
    f.unit_path,
    f.file_path,
    f.line_start,
    f.line_end,
    f.mode,
    f.padding,
    f.hash,
    f.key_size_bits,
    f.key_size_known,
    f.confidence,
    f.in_test_code,
    (a.quantum_status = 'VULNERABLE'
        and f.usage_context in ('TLS_KEY_EXCHANGE', 'KEY_AGREEMENT', 'ENCRYPTION', 'KEY_WRAP')) as hndl_exposure,
    1 as finding_count
from {{ ref('stg_finding') }} f
join {{ ref('stg_analysis_unit') }} u on u.project_key = f.project_key and u.unit_path = f.unit_path
join {{ ref('dim_project') }} p on p.project_key = f.project_key and p.is_current
join {{ ref('dim_service') }} s on s.project_key = f.project_key and s.unit_path = f.unit_path and s.is_current
join {{ ref('dim_algorithm') }} a on a.algorithm_family = f.algorithm_family
