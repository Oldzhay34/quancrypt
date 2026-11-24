select
    s.event_id,
    s.project_key,
    s.occurred_at,
    s.decision,
    s.confidence,
    s.deciding_ring,
    s.latency_ms,
    s.language
from {{ source('prep', 'scope_decision') }} s
where {{ revocation_filter('s.project_key', 's.occurred_at') }}
