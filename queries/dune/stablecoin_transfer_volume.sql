-- Daily stablecoin transfer volume on Mantle (USDT, USDC, USDe, mETH-backed)
select
  date_trunc('day', block_time) as day,
  sum(cast(value as double) / pow(10, decimals)) as value
from mantle.erc20_transfers t
inner join mantle.erc20_tokens tok on t.contract_address = tok.contract_address
where tok.symbol in ('USDT', 'USDC', 'USDe', 'FDUSD', 'DAI')
  and block_time >= now() - interval '30' day
group by 1
order by 1 desc;
