select
    u.project_key,
    u.unit_path,
    coalesce(u.java_version, 'UNKNOWN') as java_version,
    coalesce(u.spring_boot_version, 'UNKNOWN') as spring_boot_version,
    u.analysed_at,
    u.project_key || '|' || u.unit_path as service_id
from {{ source('prep', 'analysis_unit') }} u
where {{ revocation_filter('u.project_key', 'u.analysed_at') }}
