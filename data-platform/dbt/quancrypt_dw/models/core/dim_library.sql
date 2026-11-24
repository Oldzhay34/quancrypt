select {{ sk(['library']) }} as library_sk, library
from (select distinct library from {{ ref('stg_finding') }} where library is not null) l
union all
select {{ sk(["'~UNRESOLVED'"]) }}, '~UNRESOLVED'
