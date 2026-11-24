{{ config(indexes=[{'columns': ['date_key']}, {'columns': ['project_sk']}, {'columns': ['service_sk']}, {'columns': ['source_sk']}, {'columns': ['protocol_sk']}, {'columns': ['project_key']}]) }}

-- Grain: one link of the current topology of an analysis unit.
select
    l.project_key,
    l.unit_path,
    l.ordinal,
    {{ date_key('t.recorded_at') }} as date_key,
    p.project_sk,
    s.service_sk,
    {{ sk(['p.origin']) }} as source_sk,
    {{ sk(['l.protocol']) }} as protocol_sk,
    l.tls,
    l.mtls,
    1 as link_count
from {{ ref('stg_service_link') }} l
join {{ ref('stg_topology_summary') }} t on t.project_key = l.project_key and t.unit_path = l.unit_path
join {{ ref('dim_project') }} p on p.project_key = l.project_key and p.is_current
join {{ ref('dim_service') }} s on s.project_key = l.project_key and s.unit_path = l.unit_path and s.is_current
