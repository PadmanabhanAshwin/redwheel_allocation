import pandas as pd, numpy as np
D='data'; SNAP=pd.Timestamp('2026-09-07')
O=pd.read_pickle('orders_raw.pkl')
sku=O.groupby('sku')[['cls','size','trim']].first()
inv=pd.read_csv(f'{D}/plant_inventory_snapshot.csv',parse_dates=['as_of_date'])
ds=pd.read_csv(f'{D}/dealer_stock_report.csv'); ds['Count Date']=pd.to_datetime(ds['Count Date'],format='%m/%d/%Y')
cap=pd.read_csv(f'{D}/capacity_plan.csv',parse_dates=['week_start'])
F=pd.concat([pd.read_csv(f'{D}/forecast_{c}.csv',parse_dates=['week_start']).assign(channel=c) for c in ['dtc','dealer','commercial']])
print('plant inv by sku:'); pi=inv.pivot_table(index='sku',columns='location_code',values='on_hand_qty',aggfunc='sum'); pi['total']=pi.sum(1); print(pi.join(sku))
print('\ndealer stock: dealers',ds['Dealer #'].nunique(),'rows',len(ds),'count dates',ds['Count Date'].min().date(),ds['Count Date'].max().date())
print('dealers in stock report vs orders:', set(ds['Dealer #'])^set(O[O.channel=='dealer'].party))
print('dealer stock by sku:\n',ds.groupby('Item')['On Hand'].agg(['sum','median','max']))
print('outliers (>3x sku median and >=20):\n',ds[ds['On Hand']>=20].merge(ds.groupby('Item')['On Hand'].median().rename('med'),left_on='Item',right_index=True))
# capacity
print('\ncapacity weeks',cap.week_start.min().date(),cap.week_start.max().date(),'n per line',cap.groupby(['class','trim']).size().to_dict())
print('dup cap rows:',cap.duplicated(['week_start','class','trim']).sum(), ' all mondays:',(cap.week_start.dt.dayofweek==0).all())
cap['fy']=np.where(cap.week_start.dt.month>=9,cap.week_start.dt.year,cap.week_start.dt.year-1)
print(cap.pivot_table(index=['class','trim'],columns='fy',values='capacity_units',aggfunc=['min','max']))
wk=cap.week_start.sort_values().unique(); print('week gaps:',pd.Series(np.diff(wk)).value_counts().to_dict())
# forecast
print('\nforecast range',F.week_start.min().date(),F.week_start.max().date(),'rows/channel',F.groupby('channel').size().to_dict())
print('dups:',F.duplicated(['week_start','sku','channel']).sum(),' negatives:',(F.forecast_units<0).sum(), ' skus:',F.sku.nunique())
Ft=F.groupby(['week_start','sku']).forecast_units.sum().reset_index().merge(sku,left_on='sku',right_index=True)
# history weekly actual demand (order qty, by order week)
O['wk']=O.order_date-pd.to_timedelta(O.order_date.dt.dayofweek,'D')
h=O.groupby(['sku','channel']).qty.sum()/52
f13=F[F.week_start<SNAP+pd.Timedelta(weeks=13)].groupby(['sku','channel']).forecast_units.mean()
cmp=pd.DataFrame({'hist_avg_wk':h,'fcst_first13_avg':f13}).round(1); cmp['ratio']=(cmp.fcst_first13_avg/cmp.hist_avg_wk).round(2)
print('\nhistory avg weekly orders vs forecast first 13 wks:\n',cmp.unstack('channel'))
# last 13 weeks of history
h13=O[O.order_date>=SNAP-pd.Timedelta(weeks=13)].groupby('sku').qty.sum()/13
print('\nlast-13wk actual vs fcst first-13:\n',pd.DataFrame({'act_l13':h13.round(1),'fc_f13':F[F.week_start<SNAP+pd.Timedelta(weeks=13)].groupby(['sku']).forecast_units.sum()/13}).round(1))
# monthly history shape total
print('\nmonthly order units (all ch):\n',O.groupby([O.order_date.dt.to_period('M'),'cls','trim']).qty.sum().unstack([1,2]))
# demand vs capacity per line per FY
Ft['fy']=np.where(Ft.week_start.dt.month>=9,Ft.week_start.dt.year,Ft.week_start.dt.year-1)
dl=Ft.groupby(['cls','trim','fy']).forecast_units.sum()
cl=cap.groupby(['class','trim','fy']).capacity_units.sum(); cl.index.names=['cls','trim','fy']
x=pd.DataFrame({'demand':dl,'capacity':cl}); x['util']=(x.demand/x.capacity).round(2); print('\nannual demand vs capacity:\n',x)
# weekly peak check
Fw=Ft.groupby(['week_start','cls','trim']).forecast_units.sum().reset_index().merge(cap.rename(columns={'class':'cls'}),on=['week_start','cls','trim'],how='left')
Fw['over']=Fw.forecast_units>Fw.capacity_units
print('\nweeks where weekly demand > capacity:\n',Fw[Fw.over].groupby(['cls','trim']).week_start.agg(['count','min','max']))
# road carbon july spike
print('\nJuly-2027 spike rows:\n',Ft[(Ft.week_start>='2027-06-28')&(Ft.week_start<='2027-07-26')&(Ft.sku.isin(['RW-3980','RW-2984','RW-1378']))].pivot_table(index='week_start',columns='sku',values='forecast_units'))
