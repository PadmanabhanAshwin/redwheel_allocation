import pandas as pd, numpy as np, sys
D=sys.argv[1] if len(sys.argv)>1 else 'data'
SNAP=pd.Timestamp('2026-09-07')
w=pd.read_csv(f'{D}/dtc_web_orders.csv',dtype=str)
d=pd.read_csv(f'{D}/dealer_orders_export.csv',dtype=str)
c=pd.read_csv(f'{D}/Commercial_PO_Log.csv',dtype=str)
def show(name,df):
    print(f'\n##### {name}: {len(df)} rows')
    for col in df.columns:
        s=df[col]; nu=s.nunique(dropna=True)
        vals=s.value_counts(dropna=False).head(8).to_dict() if nu<=15 else f'{nu} unique; e.g. {list(s.dropna().unique()[:4])}'
        print(f'  {col:22s} null={s.isna().sum():5d}  {vals}')
show('WEB',w); show('DEALER',d); show('COMMERCIAL',c)

# normalise
W=pd.DataFrame({'channel':'dtc','order_id':w.order_id,'party':w.customer_id,'state':w.ship_to_state,
 'order_date':pd.to_datetime(w.order_date,errors='coerce'),'need_by':pd.NaT,
 'sku':w.sku,'cls':w['class'].str.lower(),'size':w['size'],'trim':w.trim.str.lower(),
 'qty':pd.to_numeric(w.qty,errors='coerce'),'price':pd.to_numeric(w.unit_price,errors='coerce'),
 'fulfilled_raw':w.is_fulfilled,'ship_date':pd.to_datetime(w.ship_date,errors='coerce')})
Dd=pd.DataFrame({'channel':'dealer','order_id':d['Dealer Order #'],'party':d['Dealer ID'],'state':d.State,
 'order_date':pd.to_datetime(d['Order Date'],format='%m/%d/%Y',errors='coerce'),'need_by':pd.to_datetime(d['Requested Ship Date'],format='%m/%d/%Y',errors='coerce'),
 'sku':d.SKU,'cls':d.Class.str.lower(),'size':d.Size,'trim':d.Trim.str.lower(),
 'qty':pd.to_numeric(d.Qty,errors='coerce'),'price':pd.to_numeric(d['Wholesale Price'],errors='coerce'),
 'fulfilled_raw':d['Fulfilled (Y/N)'],'ship_date':pd.to_datetime(d.Shipped,format='%m/%d/%Y',errors='coerce')})
C=pd.DataFrame({'channel':'commercial','order_id':c['PO Number'],'party':c.Account,'state':None,
 'order_date':pd.to_datetime(c['PO Date'],format='%d-%b-%Y',errors='coerce'),'need_by':pd.to_datetime(c['Need By'],format='%d-%b-%Y',errors='coerce'),
 'sku':c.Product,'cls':c.Class.str.lower(),'size':c.Length,'trim':c.Material.str.lower(),
 'qty':pd.to_numeric(c.Units,errors='coerce'),'price':pd.to_numeric(c['Net Price'],errors='coerce'),
 'fulfilled_raw':c.Fulfilled,'ship_date':pd.to_datetime(c.Delivered,format='%d-%b-%Y',errors='coerce')})
O=pd.concat([W,Dd,C],ignore_index=True)
O.to_pickle('orders_raw.pkl')
print('\n##### UNIFIED',len(O))
print('date parse failures:',O.order_date.isna().sum(),' qty nan:',O.qty.isna().sum())
print('order date range by channel:\n',O.groupby('channel').order_date.agg(['min','max']))
print('\nfulfilled_raw values:\n',O.groupby('channel').fulfilled_raw.value_counts(dropna=False))
print('\nduplicate order_ids:',O.order_id.duplicated().sum(), O[O.order_id.duplicated(keep=False)].groupby('channel').size().to_dict())
print('full-row dups:',O.duplicated().sum())
print('\nqty dist:\n',O.groupby('channel').qty.describe())
print('\nqty<=0:',(O.qty<=0).sum())
# SKU master consistency
m=O.groupby('sku')[['cls','size','trim']].agg(lambda s: sorted(s.dropna().unique()))
print('\nSKU attribute map:\n',m)
print('\nprices per sku/channel:\n',O.groupby(['sku','channel']).price.agg(lambda s: sorted(s.dropna().unique())).unstack())
# fulfilment logic
O['ff']=O.fulfilled_raw.str.lower().map({'true':1,'y':1,'yes':1,'false':0,'n':0,'no':0})
print('\nunmapped fulfilled flags:',O.ff.isna().sum())
print('fulfilled but no ship date:',((O.ff==1)&O.ship_date.isna()).groupby(O.channel).sum().to_dict())
print('unfulfilled but has ship date:',((O.ff==0)&O.ship_date.notna()).groupby(O.channel).sum().to_dict())
print('ship before order:',(O.ship_date<O.order_date).groupby(O.channel).sum().to_dict())
print('ship after snapshot:',(O.ship_date>SNAP).groupby(O.channel).sum().to_dict())
print('order after snapshot:',(O.order_date>SNAP).sum())
lt=(O.ship_date-O.order_date).dt.days
print('\norder->ship days:\n',lt.groupby(O.channel).describe())
# open backlog
op=O[O.ff==0]
print('\nOPEN (unfulfilled) units by channel x sku:\n',op.pivot_table(index='sku',columns='channel',values='qty',aggfunc='sum',fill_value=0))
print('\nopen order age (days before snapshot):\n',(SNAP-op.order_date).dt.days.groupby(op.channel).describe())
