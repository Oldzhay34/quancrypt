select {{ sk(['code']) }} as language_sk, code as language, description
from {{ source('prep', 'language') }}
union all
select {{ sk(["'~UNRESOLVED'"]) }}, '~UNRESOLVED', 'Not resolved'
