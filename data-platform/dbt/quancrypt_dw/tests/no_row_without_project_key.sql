-- Every row of the warehouse has a project key (warehouse-design section 4, special test 3).
select 'core.dim_project' as table_name from {{ ref('dim_project') }} where project_key is null
union all
select 'core.dim_service' as table_name from {{ ref('dim_service') }} where project_key is null
union all
select 'core.fact_crypto_finding' as table_name from {{ ref('fact_crypto_finding') }} where project_key is null
union all
select 'core.fact_topology_summary' as table_name from {{ ref('fact_topology_summary') }} where project_key is null
union all
select 'core.fact_service_link' as table_name from {{ ref('fact_service_link') }} where project_key is null
union all
select 'core.fact_scope_decision' as table_name from {{ ref('fact_scope_decision') }} where project_key is null
union all
select 'marts.mart_inventory_summary' as table_name from {{ ref('mart_inventory_summary') }} where project_key is null
union all
select 'marts.mart_service_runtime' as table_name from {{ ref('mart_service_runtime') }} where project_key is null
union all
select 'marts.mart_topology_coverage' as table_name from {{ ref('mart_topology_coverage') }} where project_key is null
union all
select 'marts.mart_risk_features' as table_name from {{ ref('mart_risk_features') }} where project_key is null
union all
select 'marts.mart_archetypes' as table_name from {{ ref('mart_archetypes') }} where project_key is null
union all
select 'snapshots.dim_project_snapshot' as table_name from {{ ref('dim_project_snapshot') }} where project_key is null
union all
select 'snapshots.dim_service_snapshot' as table_name from {{ ref('dim_service_snapshot') }} where project_key is null
