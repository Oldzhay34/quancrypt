{#- The manual path: it takes no build lock (the command line does), so run it when no build runs. Erases a project key from every warehouse table that has a project_key column (core, snapshots, marts): the KVKK deletion
    (D-317e). `dbt run-operation delete_project_key --args '{project_key: <64 hex>}'`. Normally ingest-api does this when it
    receives consent_revoked; the macro is the manual path and the test of it. -#}
{% macro delete_project_key(project_key) %}
    {% if modules.re.match('^[0-9a-f]{64}\\Z', project_key) is none %}
        {% do exceptions.raise_compiler_error("project_key must be 64 lower-case hexadecimal digits") %}
    {% endif %}
    {% set tables = run_query(
        "select c.table_schema, c.table_name from information_schema.columns c "
        "join information_schema.tables t on t.table_schema = c.table_schema and t.table_name = c.table_name "
        "where c.column_name = 'project_key' and t.table_type = 'BASE TABLE' "
        "and c.table_schema in ('core', 'snapshots', 'marts') order by 1, 2") %}
    {% for row in tables.rows %}
        {% do run_query("delete from " ~ adapter.quote(row[0]) ~ "." ~ adapter.quote(row[1]) ~ " where project_key = '" ~ project_key ~ "'") %}
        {% do log("deleted from " ~ row[0] ~ "." ~ row[1], info=true) %}
    {% endfor %}
    {% do run_query("commit") %}
{% endmacro %}
