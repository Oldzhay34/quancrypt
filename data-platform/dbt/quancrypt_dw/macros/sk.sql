{#- The surrogate key of a natural key (dbt_utils 1.4.1); a missing value is part of the key, never a NULL key. -#}
{% macro sk(columns) %}
    {{ dbt_utils.generate_surrogate_key(columns) }}
{% endmacro %}
