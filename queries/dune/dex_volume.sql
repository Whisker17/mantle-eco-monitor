-- Daily DEX volume on Mantle (all protocols)
select
  date_trunc('day', block_time) as day,
  sum(amount_usd) as value
from dex.trades
where blockchain = 'mantle'
  and block_time >= now() - interval '30' day
group by 1
order by 1 desc;
