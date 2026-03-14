-- Daily stablecoin transfer volume on Mantle
select
  date_trunc('day', evt_block_time) as day,
  sum(cast(value as double) / pow(10, tok.decimals)) as value
from erc20_mantle.evt_Transfer t
inner join tokens.erc20 tok on t.contract_address = tok.contract_address and tok.blockchain = 'mantle'
where tok.symbol in ('USDT', 'USDC', 'USDe', 'FDUSD', 'DAI')
  and evt_block_time >= now() - interval '30' day
group by 1
order by 1 desc
