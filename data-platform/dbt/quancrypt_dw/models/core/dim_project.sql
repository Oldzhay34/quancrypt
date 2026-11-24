{{ config(indexes=[{'columns': ['project_key']}]) }}

select
    {{ sk(['project_key', 'dbt_valid_from']) }} as project_sk,
    project_key,
    origin,
    is_outlier_project,
    dbt_valid_from as valid_from,
    dbt_valid_to as valid_to,
    dbt_valid_to is null as is_current
from {{ ref('dim_project_snapshot') }}
