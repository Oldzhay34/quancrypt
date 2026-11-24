select {{ sk(['code']) }} as deciding_ring_sk, code as deciding_ring, sort_order, description
from {{ source('prep', 'deciding_ring') }}
union all
select {{ sk(["'~UNRESOLVED'"]) }}, '~UNRESOLVED', 99, 'Not resolved'
