-- Daily Active Users on Mantle
-- Returns distinct sending addresses per day
select
  date_trunc('day', block_time) as day,
  count(distinct "from") as value
from mantle.transactions
where block_time >= now() - interval '30' day
group by 1
order by 1 desc;
