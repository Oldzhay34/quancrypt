select {{ sk(['code']) }} as protocol_sk, code as protocol, description
from {{ source('prep', 'protocol') }}
union all
select {{ sk(["'~UNRESOLVED'"]) }}, '~UNRESOLVED', 'Not resolved'
