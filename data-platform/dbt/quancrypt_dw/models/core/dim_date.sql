-- One row per calendar day 2024-01-01 to 2030-12-31 and the unknown day 1900-01-01 (D-316e, D-317c).
with days as (
    {{ dbt_utils.date_spine(datepart="day", start_date="cast('2024-01-01' as date)", end_date="cast('2031-01-01' as date)") }}
), all_days as (
    select cast(date_day as date) as date_day from days
    union all
    select date '1900-01-01'
)
select
    to_char(date_day, 'YYYYMMDD')::int as date_key,
    date_day,
    extract(year from date_day)::int as year,
    extract(quarter from date_day)::int as quarter,
    extract(month from date_day)::int as month,
    (array['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'])[extract(month from date_day)::int] as month_name_tr,
    trim(to_char(date_day, 'Month')) as month_name_en,
    extract(week from date_day)::int as iso_week,
    extract(isodow from date_day)::int as day_of_week,
    extract(isodow from date_day) in (6, 7) as is_weekend
from all_days
