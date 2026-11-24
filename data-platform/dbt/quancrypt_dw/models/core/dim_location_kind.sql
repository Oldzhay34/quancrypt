select {{ sk(['code']) }} as location_kind_sk, code as location_kind, description, code = 'TEST_CODE' as is_test_code
from {{ source('prep', 'location_kind') }}
union all
select {{ sk(["'~UNRESOLVED'"]) }}, '~UNRESOLVED', 'Not resolved', false
