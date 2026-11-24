select
    {{ sk(['a.code']) }} as algorithm_sk,
    a.code as algorithm_family,
    q.quantum_status,
    a.description
from {{ source('prep', 'algorithm_family') }} a
join {{ ref('quantum_status') }} q on q.algorithm_family = a.code
