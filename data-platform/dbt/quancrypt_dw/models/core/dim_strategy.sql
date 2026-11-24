select {{ sk(['strategy_code']) }} as strategy_sk, strategy_code, description, nullif(related_priority, '') as related_priority
from {{ ref('strategy') }}
union all
select {{ sk(["'~UNRESOLVED'"]) }}, '~UNRESOLVED', 'Not resolved', null
