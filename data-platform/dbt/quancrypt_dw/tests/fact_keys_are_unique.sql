-- Composite keys of the facts without a single id.
select 'fact_topology_summary' as fact, project_key || '|' || unit_path as key
from {{ ref('fact_topology_summary') }} group by project_key, unit_path having count(*) > 1
union all
select 'fact_service_link', project_key || '|' || unit_path || '|' || ordinal
from {{ ref('fact_service_link') }} group by project_key, unit_path, ordinal having count(*) > 1
