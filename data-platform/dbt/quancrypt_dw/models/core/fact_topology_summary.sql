{{ config(indexes=[{'columns': ['date_key']}, {'columns': ['project_sk']}, {'columns': ['service_sk']}, {'columns': ['source_sk']}, {'columns': ['project_key']}]) }}

-- Grain: the current topology summary of one analysis unit (a snapshot of the current state).
select
    t.project_key,
    t.unit_path,
    {{ date_key('t.recorded_at') }} as date_key,
    p.project_sk,
    s.service_sk,
    {{ sk(['p.origin']) }} as source_sk,
    t.source_event_id,
    t.node_count,
    t.edge_count,
    t.tls_edge_count,
    t.mtls_edge_count
from {{ ref('stg_topology_summary') }} t
join {{ ref('dim_project') }} p on p.project_key = t.project_key and p.is_current
join {{ ref('dim_service') }} s on s.project_key = t.project_key and s.unit_path = t.unit_path and s.is_current
