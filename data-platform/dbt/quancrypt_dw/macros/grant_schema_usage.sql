{#- Schema level privileges (table level ones come from the `grants` config of the models): the application role reads and
    erases in core, snapshots and marts; warehouse_reader reads marts only (D-24, D-319e). A schema that does not exist yet
    (a partial run) is skipped. -#}
{% macro grant_schema_usage() %}
    {% if execute %}
    {% for schema in ['core', 'snapshots', 'marts'] %}
        {% if run_query("select to_regnamespace('" ~ schema ~ "') is not null").rows[0][0] %}
            {% do run_query("grant usage on schema " ~ schema ~ " to warehouse_db_app") %}
        {% endif %}
    {% endfor %}
    {% if run_query("select to_regnamespace('marts') is not null").rows[0][0] %}
        {% do run_query("grant usage on schema marts to warehouse_reader") %}
    {% endif %}
    {% endif %}
{% endmacro %}
