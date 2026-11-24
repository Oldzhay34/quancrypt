select
    f.id as finding_id,
    f.project_key,
    f.unit_path,
    f.source_event_id,
    f.file_path,
    f.line_start,
    f.line_end,
    f.algorithm_family,
    f.usage_context,
    f.location_kind,
    f.priority,
    f.key_size_bits,
    f.key_size_known,
    f.mode,
    f.padding,
    f.hash,
    f.library,
    f.confidence,
    f.in_test_code
from {{ source('prep', 'finding') }} f
join {{ ref('stg_analysis_unit') }} u on u.project_key = f.project_key and u.unit_path = f.unit_path
