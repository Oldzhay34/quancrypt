-- Only the unresolved member until the model outputs (P7) and the migration steps (phase 8) exist.
select
    {{ sk(["'~UNRESOLVED'", "'~UNRESOLVED'"]) }} as model_sk,
    '~UNRESOLVED' as model_name,
    '~UNRESOLVED' as model_version,
    'UNKNOWN' as task
