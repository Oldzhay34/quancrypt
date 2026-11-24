select {{ sk(['code']) }} as source_sk, code as origin, description
from {{ source('prep', 'project_origin') }}
union all
select {{ sk(["'~UNRESOLVED'"]) }}, '~UNRESOLVED', 'Not resolved'
