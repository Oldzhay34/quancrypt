{{ config(indexes=[{'columns': ['project_key']}]) }}

select
    {{ sk(['project_key', 'unit_path', 'dbt_valid_from']) }} as service_sk,
    project_key,
    unit_path,
    java_version,
    case
        when java_version ~ '^1\.[0-9]+' then (regexp_match(java_version, '^1\.([0-9]+)'))[1]::int
        when java_version ~ '^[0-9]+' then (regexp_match(java_version, '^([0-9]+)'))[1]::int
    end as java_major,
    spring_boot_version,
    dbt_valid_from as valid_from,
    dbt_valid_to as valid_to,
    dbt_valid_to is null as is_current
from {{ ref('dim_service_snapshot') }}
