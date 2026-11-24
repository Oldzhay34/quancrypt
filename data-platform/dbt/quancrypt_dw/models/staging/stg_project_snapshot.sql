-- A project stays when any of its rows passes the revocation filter (a unit, a topology or a scope decision, D-318c).
select
    p.project_key,
    p.origin,
    p.is_outlier_project
from {{ source('prep', 'project_snapshot') }} p
where exists (select 1 from {{ ref('stg_analysis_unit') }} u where u.project_key = p.project_key)
   or exists (select 1 from {{ ref('stg_scope_decision') }} s where s.project_key = p.project_key)
