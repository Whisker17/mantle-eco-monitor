-- Daily Active Users on Mantle
-- Returns distinct sending addresses per day
select
  date_trunc('day', block_time) as day,
  count(distinct "from") as value
from mantle.transactions
where block_time >= cast('{{start_date}}' as timestamp)
  and block_time < cast('{{end_date}}' as timestamp) + interval '1' day
group by 1
order by 1 asc;
