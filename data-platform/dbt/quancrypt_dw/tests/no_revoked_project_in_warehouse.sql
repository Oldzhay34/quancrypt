-- A project key whose consent was revoked has no warehouse row unless prep (read as it is, not through the filtered
-- staging views) still holds a row of the key newer than the revocation (KVKK, D-317e, D-318c).
select 'core.dim_project' as warehouse_table, w.project_key
from {{ ref('dim_project') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'core.dim_service' as warehouse_table, w.project_key
from {{ ref('dim_service') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'core.fact_crypto_finding' as warehouse_table, w.project_key
from {{ ref('fact_crypto_finding') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'core.fact_topology_summary' as warehouse_table, w.project_key
from {{ ref('fact_topology_summary') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'core.fact_service_link' as warehouse_table, w.project_key
from {{ ref('fact_service_link') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'core.fact_scope_decision' as warehouse_table, w.project_key
from {{ ref('fact_scope_decision') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'marts.mart_inventory_summary' as warehouse_table, w.project_key
from {{ ref('mart_inventory_summary') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'marts.mart_service_runtime' as warehouse_table, w.project_key
from {{ ref('mart_service_runtime') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'marts.mart_topology_coverage' as warehouse_table, w.project_key
from {{ ref('mart_topology_coverage') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'marts.mart_risk_features' as warehouse_table, w.project_key
from {{ ref('mart_risk_features') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'snapshots.dim_project_snapshot' as warehouse_table, w.project_key
from {{ ref('dim_project_snapshot') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
union all
select 'snapshots.dim_service_snapshot' as warehouse_table, w.project_key
from {{ ref('dim_service_snapshot') }} w
join {{ source('ingest', 'ingest_audit') }} a on a.project_key = w.project_key
where not exists (select 1 from {{ source('prep', 'analysis_unit') }} u
                  where u.project_key = w.project_key and u.analysed_at > a.revoked_at)
  and not exists (select 1 from {{ source('prep', 'scope_decision') }} s
                  where s.project_key = w.project_key and s.occurred_at > a.revoked_at)
