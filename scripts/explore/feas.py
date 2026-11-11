import pandas as pd, numpy as np
D='data'; SNAP=pd.Timestamp('2026-09-07')
O=pd.read_pickle('orders_raw.pkl'); O['ff']=O.fulfilled_raw.str.lower().isin(['true','y','yes'])
sku=O.groupby('sku')[['cls','trim']].first()
bl=O[(~O.ff)|(O.ship_date>SNAP)].groupby('sku').qty.sum()
inv=pd.read_csv(f'{D}/plant_inventory_snapshot.csv').groupby('sku').on_hand_qty.sum()
cap=pd.read_csv(f'{D}/capacity_plan.csv',parse_dates=['week_start'])
F=pd.concat([pd.read_csv(f'{D}/forecast_{c}.csv',parse_dates=['week_start']) for c in ['dtc','dealer','commercial']]).groupby(['week_start','sku']).forecast_units.sum().unstack()
grp=lambda s: 'road' if sku.loc[s,'cls']=='road' else f"mtb_{sku.loc[s,'trim']}"
G={g:[s for s in F.columns if grp(s)==g] for g in ['road','mtb_base','mtb_carbon']}
net0=(inv.reindex(F.columns,fill_value=0)-bl.reindex(F.columns,fill_value=0))
print('net position at snapshot (inv-backlog):',net0.to_dict())
capw=cap.assign(g=np.where(cap['class']=='road','road','mtb_'+cap.trim)).groupby(['week_start','g']).capacity_units.sum().unstack()
weeks=capw.index
def cover(net,dem,i):  # forward weeks covered by net position starting week i+1
    if net<=0: return net/dem.iloc[i+1:i+5].mean()  # negative: backlog in weeks of avg demand
    c=0; rem=net
    for d in dem.iloc[i+1:]:
        if rem>=d: rem-=d; c+=1
        else: return c+rem/d
    return c
for g,ss in G.items():
    dem=F[ss].sum(1); net=net0[ss].sum(); out=[]
    for i,w in enumerate(weeks):
        net+=capw.loc[w,g]-dem.loc[w]; out.append((w,net,cover(net,dem,dem.index.get_loc(w))))
    o=pd.DataFrame(out,columns=['wk','net','wos']).set_index('wk')
    tgt=np.where(g=='road',np.where(o.index>='2028-01-01',10,8),12 if g=='mtb_base' else 15)
    hit=o.index[o.wos>=tgt]
    print(f"\n{g}: start net {net0[ss].sum()}, start WOS {cover(net0[ss].sum(),dem,0):.1f}, first week target met at max build: {hit.min().date() if len(hit) else 'never'}")
    print(o.iloc[[0,4,8,13,17,26,39,52,65,78,104,120]].round(1).T)
