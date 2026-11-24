{#- yyyymmdd of a UTC time; no time or a day outside the calendar of dim_date is 19000101 (D-317c). -#}
{% macro date_key(timestamp_column) %}
    case
        when {{ timestamp_column }} is null then 19000101
        when (({{ timestamp_column }} at time zone 'UTC')::date) between date '2024-01-01' and date '2030-12-31'
            then to_char({{ timestamp_column }} at time zone 'UTC', 'YYYYMMDD')::int
        else 19000101
    end
{% endmacro %}
