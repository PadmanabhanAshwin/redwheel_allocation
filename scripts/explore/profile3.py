import pandas as pd, numpy as np
D='data'; SNAP=pd.Timestamp('2026-09-07')
O=pd.read_pickle('orders_raw.pkl')
O['ff']=O.fulfilled_raw.str.lower().isin(['true','y','yes'])
F=pd.concat([pd.read_csv(f'{D}/forecast_{c}.csv',parse_dates=['week_start']).assign(channel=c) for c in ['dtc','dealer','commercial']])
print('DTC sku coverage:',O[O.channel=='dtc'].sku.value_counts().to_dict())
# YoY: actual Sep25-Aug26 vs forecast Sep26-Aug27, by sku x channel
fy1=F[F.week_start<'2027-09-06'].groupby(['sku','channel']).forecast_units.sum()
act=O.groupby(['sku','channel']).qty.sum()
y=pd.DataFrame({'act_FY25':act,'fc_FY26':fy1}); y['growth']=(y.fc_FY26/y.act_FY25-1).round(2)
print('\nYoY actual 12m vs forecast next 12m:\n',y.unstack('channel')['growth'], '\nTotal by sku:\n',(y.groupby('sku').sum().eval('fc_FY26/act_FY25-1')).round(2))
# same-season: actual Sep8-Dec 2025 vs forecast Sep7-Dec 2026
a=O[(O.order_date<'2025-12-31')].groupby('sku').qty.sum(); f=F[F.week_start<'2026-12-28'].groupby('sku').forecast_units.sum()
print('\nSep-Dec 2025 actual vs Sep-Dec 2026 fcst:\n',pd.DataFrame({'act':a,'fc':f,'r':(f/a).round(2)}))
# monthly by sku for 9324 and fulfilment rate trend
O['m']=O.order_date.dt.to_period('M')
print('\nfill rate (share of order units fulfilled) by order month x sku:\n',(O.assign(fq=O.qty*O.ff).groupby(['m','sku']).fq.sum()/O.groupby(['m','sku']).qty.sum()).unstack().round(2))
print('\nRW-9324 monthly orders by channel:\n',O[O.sku=='RW-9324'].groupby(['m','channel']).qty.sum().unstack())
# true backlog as of snapshot: unfulfilled OR shipped after snap
O['open_at_snap']=(~O.ff)|(O.ship_date>SNAP)
print('\nshipped after snapshot:\n',O[O.ship_date>SNAP][['channel','order_id','order_date','ship_date','sku','qty']])
b=O[O.open_at_snap].groupby('sku').qty.sum(); print('\nbacklog units at snap by sku:',b.to_dict(),' total',b.sum())
# dealer requested ship date of open orders: past due?
od=O[O.open_at_snap&O.need_by.notna()]; print('\nopen dealer/commercial orders past need-by at snap:',(od.need_by<SNAP).sum(),'of',len(od))
print('need_by-order_date days:',(O.need_by-O.order_date).dt.days.describe().round(1).to_dict())
