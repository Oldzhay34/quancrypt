-- Q8. Grain: day x language x deciding ring. Only the distribution of decisions: the false refusal rate needs the labelled
-- set of P7.1 (D-316g). No project column: the totals of a revoked project leave at the next build.
select
    d.date_day,
    l.language,
    r.deciding_ring,
    sum(f.decision_count) as decision_count,
    sum(f.is_denied::int) as denied_count,
    sum(f.is_denied::int)::numeric / nullif(sum(f.decision_count), 0) as denied_ratio,
    avg(f.confidence) as avg_confidence,
    avg(f.latency_ms) as avg_latency_ms,
    percentile_cont(0.95) within group (order by f.latency_ms) as p95_latency_ms
from {{ ref('fact_scope_decision') }} f
join {{ ref('dim_date') }} d on d.date_key = f.date_key
join {{ ref('dim_language') }} l on l.language_sk = f.language_sk
join {{ ref('dim_deciding_ring') }} r on r.deciding_ring_sk = f.deciding_ring_sk
group by d.date_day, l.language, r.deciding_ring
