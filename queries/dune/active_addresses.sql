-- Active Addresses on Mantle (distinct senders + receivers)
select
  date_trunc('day', block_time) as day,
  count(distinct address) as value
from (
  select block_time, "from" as address from mantle.transactions
  union all
  select block_time, "to" as address from mantle.transactions where "to" is not null
) combined
where block_time >= cast('{{start_date}}' as timestamp)
  and block_time < cast('{{end_date}}' as timestamp) + interval '1' day
group by 1
order by 1 asc;
