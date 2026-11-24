-- At most one current row per project and per service (warehouse-design section 4, special test 2); the dimension rows of
-- every staged project and unit exist (a fact would otherwise lose its join).
select 'dim_project' as dimension, project_key as natural_key from {{ ref('dim_project') }}
where is_current group by project_key having count(*) > 1
union all
select 'dim_service', project_key || '|' || unit_path from {{ ref('dim_service') }}
where is_current group by project_key, unit_path having count(*) > 1
union all
select 'dim_project missing', p.project_key from {{ ref('stg_project_snapshot') }} p
where not exists (select 1 from {{ ref('dim_project') }} d where d.project_key = p.project_key and d.is_current)
union all
select 'dim_service missing', u.service_id from {{ ref('stg_analysis_unit') }} u
where not exists (select 1 from {{ ref('dim_service') }} d where d.project_key = u.project_key and d.unit_path = u.unit_path and d.is_current)
