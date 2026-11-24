{{ config(indexes=[{'columns': ['date_key']}, {'columns': ['project_sk']}, {'columns': ['strategy_sk']}, {'columns': ['model_sk']}, {'columns': ['project_key']}]) }}

-- Grain: one attempt of a plan item (phase 8). No source exists yet: the table is defined and empty (D-319i).
select
    cast(null as varchar(64)) as step_id,
    cast(null as integer) as date_key,
    cast(null as varchar(32)) as project_sk,
    cast(null as varchar(32)) as strategy_sk,
    cast(null as varchar(32)) as model_sk,
    cast(null as varchar(64)) as project_key,
    cast(null as uuid) as finding_id,
    cast(null as integer) as changed_lines,
    cast(null as boolean) as build_ok,
    cast(null as boolean) as tests_ok,
    cast(null as boolean) as handshake_ok,
    cast(null as integer) as duration_ms,
    cast(null as integer) as llm_tokens,
    cast(null as numeric(5, 4)) as predicted_success
where false
