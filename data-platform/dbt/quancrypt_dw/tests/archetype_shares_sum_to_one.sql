-- depends_on: {{ ref('mart_archetypes') }}
-- The family shares and the context shares of a project profile each add up to one (P7.4, D-338a).
{%- set columns = adapter.get_columns_in_relation(ref('mart_archetypes')) if execute else [] %}
{%- set families = [] %}
{%- set contexts = [] %}
{%- for column in columns %}
    {%- if column.name.startswith('share_alg_') %}{% do families.append(column.name) %}{% endif %}
    {%- if column.name.startswith('share_ctx_') %}{% do contexts.append(column.name) %}{% endif %}
{%- endfor %}
select project_key
from {{ ref('mart_archetypes') }}
where abs(({{ families | join(' + ') if families else '1' }}) - 1) > 1e-9
   or abs(({{ contexts | join(' + ') if contexts else '1' }}) - 1) > 1e-9
