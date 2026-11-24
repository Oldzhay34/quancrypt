{#- The KVKK filter of the staging models (D-317e, D-318c): a row is kept when its time is after the latest consent
    revocation of its project key (ingest.ingest_audit), so a build that read prep before an erasure cannot bring the erased
    data back. `ingest_audit` is the one table outside prep a staging model reads. -#}
{% macro revocation_filter(project_key_column, time_column) %}
    not exists (
        select 1
        from {{ source('ingest', 'ingest_audit') }} a
        where a.project_key = {{ project_key_column }}
          and a.revoked_at >= {{ time_column }}
    )
{% endmacro %}
