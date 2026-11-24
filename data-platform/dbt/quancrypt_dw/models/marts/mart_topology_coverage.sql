{{ config(indexes=[{'columns': ['project_key']}]) }}

-- Q5. Grain: one project. A ratio uses only the units whose source counted TLS edges (tls_edge_count is not null): both the
-- numerator and the denominator come from those rows (docs/data/warehouse-design.md section 5).
select
    p.project_key,
    p.origin,
    count(*) as unit_count,
    sum(t.node_count) as node_count,
    sum(t.edge_count) as edge_count,
    sum(t.tls_edge_count) as tls_edge_count,
    sum(t.mtls_edge_count) as mtls_edge_count,
    sum(t.edge_count) filter (where t.tls_edge_count is not null) as edges_with_tls_info,
    sum(t.tls_edge_count)::numeric
        / nullif(sum(t.edge_count) filter (where t.tls_edge_count is not null), 0) as tls_ratio,
    sum(t.mtls_edge_count)::numeric
        / nullif(sum(t.edge_count) filter (where t.mtls_edge_count is not null), 0) as mtls_ratio
from {{ ref('fact_topology_summary') }} t
join {{ ref('dim_project') }} p on p.project_sk = t.project_sk
group by p.project_key, p.origin
