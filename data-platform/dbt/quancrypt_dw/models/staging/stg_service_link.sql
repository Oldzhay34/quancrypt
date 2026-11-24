select
    l.project_key,
    l.unit_path,
    l.ordinal,
    l.protocol,
    l.tls,
    l.mtls
from {{ source('prep', 'service_link') }} l
join {{ ref('stg_topology_summary') }} t on t.project_key = l.project_key and t.unit_path = l.unit_path
