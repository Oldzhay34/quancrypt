{{ config(indexes=[{'columns': ['date_key']}, {'columns': ['project_sk']}, {'columns': ['language_sk']}, {'columns': ['deciding_ring_sk']}, {'columns': ['project_key']}]) }}

-- Grain: one decision of the scope guard for one user request (the request text is never stored).
select
    d.event_id,
    {{ date_key('d.occurred_at') }} as date_key,
    p.project_sk,
    {{ sk(['d.language']) }} as language_sk,
    {{ sk(['d.deciding_ring']) }} as deciding_ring_sk,
    d.project_key,
    d.occurred_at,
    d.decision,
    d.decision = 'DENY' as is_denied,
    d.confidence,
    d.latency_ms,
    1 as decision_count
from {{ ref('stg_scope_decision') }} d
join {{ ref('dim_project') }} p on p.project_key = d.project_key and p.is_current
