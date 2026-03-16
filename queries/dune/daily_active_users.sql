-- Daily Active Users on Mantle
-- Returns 7-day rolling average of distinct sending addresses per day
with daily_senders as (
  select
    date_trunc('day', block_time) as day,
    count(distinct "from") as senders
  from mantle.transactions
  where block_time >= cast('{{start_date}}' as timestamp) - interval '6' day
    and block_time < cast('{{end_date}}' as timestamp) + interval '1' day
  group by 1
)
select
  day,
  avg(senders) over (
    order by day
    rows between 6 preceding and current row
  ) as value
from daily_senders
where day >= cast('{{start_date}}' as timestamp)
  and day < cast('{{end_date}}' as timestamp) + interval '1' day
order by 1 asc;
