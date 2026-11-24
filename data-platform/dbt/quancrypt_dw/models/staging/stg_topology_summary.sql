select
    t.project_key,
    t.unit_path,
    t.source_event_id,
    t.node_count,
    t.edge_count,
    t.tls_edge_count,
    t.mtls_edge_count,
    t.recorded_at
from {{ source('prep', 'topology_summary') }} t
join {{ ref('stg_analysis_unit') }} u on u.project_key = t.project_key and u.unit_path = t.unit_path
where {{ revocation_filter('t.project_key', 't.recorded_at') }}
