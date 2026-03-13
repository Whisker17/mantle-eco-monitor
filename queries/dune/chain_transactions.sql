-- Daily transaction count on Mantle
select
  date_trunc('day', block_time) as day,
  count(*) as value
from mantle.transactions
where block_time >= now() - interval '30' day
group by 1
order by 1 desc;
