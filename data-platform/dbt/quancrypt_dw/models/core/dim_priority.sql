select {{ sk(['code']) }} as priority_sk, code as priority, sort_order, description
from {{ source('prep', 'priority') }}
union all
select {{ sk(["'~UNRESOLVED'"]) }}, '~UNRESOLVED', 99, 'Not resolved'
