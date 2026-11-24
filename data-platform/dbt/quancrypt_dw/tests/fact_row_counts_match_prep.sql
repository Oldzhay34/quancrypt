-- The facts hold exactly the rows prep holds after the revocation filter (warehouse-design section 4, special test 1).
select 'fact_crypto_finding' as fact, (select count(*) from {{ ref('fact_crypto_finding') }}) as actual,
       (select count(*) from {{ ref('stg_finding') }}) as expected
where (select count(*) from {{ ref('fact_crypto_finding') }}) <> (select count(*) from {{ ref('stg_finding') }})
union all
select 'fact_topology_summary', (select count(*) from {{ ref('fact_topology_summary') }}),
       (select count(*) from {{ ref('stg_topology_summary') }})
where (select count(*) from {{ ref('fact_topology_summary') }}) <> (select count(*) from {{ ref('stg_topology_summary') }})
union all
select 'fact_service_link', (select count(*) from {{ ref('fact_service_link') }}), (select count(*) from {{ ref('stg_service_link') }})
where (select count(*) from {{ ref('fact_service_link') }}) <> (select count(*) from {{ ref('stg_service_link') }})
union all
select 'fact_scope_decision', (select count(*) from {{ ref('fact_scope_decision') }}),
       (select count(*) from {{ ref('stg_scope_decision') }})
where (select count(*) from {{ ref('fact_scope_decision') }}) <> (select count(*) from {{ ref('stg_scope_decision') }})
