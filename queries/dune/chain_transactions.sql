-- Daily transaction count on Mantle
select
  date_trunc('day', block_time) as day,
  count(*) as value
from mantle.transactions
where block_time >= cast('{{start_date}}' as timestamp)
  and block_time < cast('{{end_date}}' as timestamp) + interval '1' day
group by 1
order by 1 asc;
