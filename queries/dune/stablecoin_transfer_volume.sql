-- Daily stablecoin transfer volume on Mantle
-- Uses explicit contract addresses for the tracked stablecoins.
with stablecoins as (
  select 0x201eba5cc46d216ce6dc03f6a759e8e766e956ae as contract_address, 'USDT' as symbol, 6 as decimals
  union all
  select 0x5d3a1ff2b6bab83b63cd9ad0787074081a52ef34 as contract_address, 'USDe' as symbol, 18 as decimals
  union all
  select 0x09bc4e0d864854c6afb6eb9a9cdf58ac190d0df9 as contract_address, 'USDC' as symbol, 6 as decimals
  union all
  select 0x5be26527e817998a7206475496fde1e68957c5a6 as contract_address, 'USDY' as symbol, 18 as decimals
  union all
  select 0x00000000efe302beaa2b3e6e1b18d08d69a9012a as contract_address, 'AUSD' as symbol, 6 as decimals
  union all
  select 0x894134a25a5fac1c2c26f1d8fbf05111a3cb9487 as contract_address, 'GRAI' as symbol, 18 as decimals
)
select
  date_trunc('day', t.evt_block_time) as day,
  s.symbol,
  cast(t.contract_address as varchar) as contract_address,
  sum(cast(t.value as double) / pow(10, s.decimals)) as volume,
  count(distinct t.evt_tx_hash) as tx_count,
  count(*) as transfer_count
from erc20_mantle.evt_Transfer t
join stablecoins s
  on t.contract_address = s.contract_address
where t.evt_block_time >= cast('{{start_date}}' as timestamp)
  and t.evt_block_time < cast('{{end_date}}' as timestamp) + interval '1' day
  and t."from" != 0x0000000000000000000000000000000000000000
  and t."to" != 0x0000000000000000000000000000000000000000
group by 1, 2, 3
order by 1 asc, volume desc;
