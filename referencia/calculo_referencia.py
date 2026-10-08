"""Port de referencia (mínimo, sin optimizar) de la lógica de valuación del tablero actual.
Sirve para entender las reglas y para generar los valores de control de los tests. No es código de producción.
Uso: python3 calculo_referencia.py ejemplo/precios_diarios.json ejemplo/tenencias.json ejemplo/movimientos.json > ejemplo/valores_control.json
"""
import json, datetime as dt, sys
U=lambda p: json.load(open(p,encoding="utf-8"))  # UTF-8 explícito: en Windows el default es otro y "Minería" dejaría de coincidir
SER=U(sys.argv[1])["serie"]; TEN=U(sys.argv[2]); MOV=U(sys.argv[3])
P=lambda s: dt.date.fromisoformat(s)
A=[dict(t=a["ticker"],tipo=a["tipo"],c=a["grupo"],q=a["cantidad"],ars=a["cotiza_en_pesos"],fixed=a["valor_fijo_usd"]) for a in TEN["activos"]]
OPS=[dict(d=m["fecha"],tipo=m["tipo"],t=m["activo"],q=m["cantidad"],usd=m.get("usd"),flow=m.get("flujo_usd") or 0,noQty=m.get("sin_efecto_en_saldo",False),daily=m.get("devengo_diario"),dest=m.get("destino")) for m in MOV["movimientos"]]
INM=TEN["inmuebles"]; PAS=TEN["pasivos"]; M=TEN["mineros"]
def days(a,b): return (P(b)-P(a)).days
def bval(x,d):
    if d<x["fecha_compra"]:
        return sum(-o["flow"] for o in OPS if o["dest"]==x["nombre"] and o["flow"] and o["d"]<=d)
    dep=x.get("depreciacion_anual_pct") or 0
    if dep:
        base=x.get("valor_nuevo_usd") or x["costo_usd"]
        return max(0,base*(1-dep/100*days(x["fecha_compra"],d)/365.25))
    return x["valor_usd"]
def inm(d): return sum(bval(x,d) for x in INM)
def cu(p): return p["alicuota_ars"]/p["mep_referencia"]
def canc(p): return p.get("cuotas_canceladas") or []
def pend(p,d): return p["cuotas_total"]-sum(1 for c in p["cuotas_pagas"] if c["fecha"]<=d)-sum(1 for c in canc(p) if c["fecha"]<=d)
def deu(d): return sum(0 if d<p["fecha_alta"] else pend(p,d)*cu(p) for p in PAS)
def addy(s,n): x=P(s); return x.replace(year=x.year+n).isoformat()
def minval(d):
    s=0
    for t in M["compras"]:
        if d<t["fecha"]: continue
        fin=addy(t["fecha"],M["vida_util_anios"])
        x=min(1,days(t["fecha"],d)/days(t["fecha"],fin))
        ini,res=M["valor_inicial_pct"]/100,M["valor_residual_pct"]/100
        s+=t["costo_usd"]*(ini-(ini-res)*x)
    return s
def after(o,date):
    if not o["daily"]: return o["q"] if o["d"]>date else 0
    if date>=o["d"]: return 0
    if date<o["daily"]["desde"]: return o["q"]
    return o["daily"]["por_dia"]*days(date,o["d"])
def qat(a,date): return a["q"]-sum(after(o,date) for o in OPS if o["t"]==a["t"] and not o["noQty"])
rows=[]
for r in SER:
    t,mep=r["fecha"],r["mep"]; pos={}
    for a in A:
        pu=1 if a["fixed"] else ((r["ars"].get(a["t"]) or 0)/mep if a["ars"] else r["btc_usdt"])
        pos[a["t"]]=qat(a,t)*pu
    tot=sum(pos.values()); mn=minval(t); im=inm(t); de=deu(t)
    rows.append(dict(t=t,tot=tot,min=mn,inm=im,deu=de,pat=tot+mn+im-de,pos=pos))
idx=idxP=1;cf=cfP=0
for i,r in enumerate(rows):
    t=r["t"]
    if i:
        fl=sum(o["flow"] for o in OPS if o["flow"] and o["d"]==t)
        flP=fl-sum(o["flow"] for o in OPS if o["flow"] and o["d"]==t and o["tipo"] in("Minería","Costo minería"))
        flP+=sum(c["costo_usd"] for c in M["compras"] if c["fecha"]==t)
        flP+=sum(sum(1 for c in p["cuotas_pagas"] if c["fecha"]==t)*cu(p) for p in PAS if t>=p["fecha_alta"])
        # cuotas canceladas: si no se pagaron desde la cartera son aporte al patrimonio, como una cuota paga
        flP+=sum(sum(1 for c in canc(p) if c["fecha"]==t and not c.get("pagada_desde_cartera"))*cu(p) for p in PAS if t>=p["fecha_alta"])
        flP-=sum(o["flow"] for o in OPS if o["flow"] and o["dest"] and o["dest"]!="Mineros" and o["d"]==t)
        p=rows[i-1]; idx*=(r["tot"]-fl)/p["tot"]; idxP*=(r["pat"]-flP)/p["pat"]
    else: fl=flP=0
    cf+=fl;cfP+=flP
    r.update(flow=fl,flowP=flP,cumF=cf,cumFP=cfP,idx=idx,idxP=idxP,capT=rows[0]["tot"]+cf,capP=rows[0]["pat"]+cfP)
out={}
def FECHAS_CONTROL(rows):
    ts=[r["t"] for r in rows]
    fin_mes=[t for i,t in enumerate(ts) if i==len(ts)-1 or ts[i+1][:7]!=t[:7]]
    clave=sorted({o["d"] for o in OPS}|{c["fecha"] for c in M["compras"]}|{x["fecha_compra"] for x in INM}|{c["fecha"] for p in PAS for c in p["cuotas_pagas"]}|{c["fecha"] for p in PAS for c in canc(p)})
    return sorted({ts[0],*fin_mes,*[t for t in clave if t in ts]})
for d in FECHAS_CONTROL(rows):
    r=next(x for x in rows if x["t"]==d)
    out[d]={k:round(r[k],2) for k in("tot","min","inm","deu","pat","flow","flowP","capT","capP")}
    out[d]["rend_cartera_pct"]=round((r["idx"]-1)*100,2); out[d]["rend_patrimonio_pct"]=round((r["idxP"]-1)*100,2)
    out[d]["posiciones"]={k:round(v,2) for k,v in r["pos"].items() if abs(v)>=0.005}

# --- costo promedio en USD de las posiciones abiertas (método promedio ponderado; se reinicia cuando la cantidad vuelve a 0)
COST={}
for a in A:
    if a["fixed"]: continue
    os_=sorted([o for o in OPS if o["t"]==a["t"] and not o["noQty"] and not o["daily"]],key=lambda o:o["d"])
    if not os_: continue
    d0=(P(os_[0]["d"])-dt.timedelta(1)).isoformat(); q=qat(a,d0); c=0; ok=abs(q)<1e-9
    for o in os_:
        if o["q"]>0: q+=o["q"]; c+=o["usd"] or 0
        else:
            avg=c/q if q>0 else 0; c-=avg*(-o["q"]); q+=o["q"]
            if abs(q)<1e-9: q=0;c=0;ok=True
    if ok and a["q"]>0: COST[a["t"]]={"costo_usd":round(c,2),"costo_promedio":round(c/q,6)}
mineria={"btc_minado":round(sum(o["q"] for o in OPS if o["tipo"]=="Minería"),8),"usd_al_cobrar":round(sum(o["usd"] or 0 for o in OPS if o["tipo"]=="Minería"),2),"costos_usd":round(sum(o["usd"] for o in OPS if o["tipo"]=="Costo minería"),2)}
print(json.dumps({"_descripcion":"Valores de control generados por calculo_referencia.py con los datos FICTICIOS de esta carpeta. tot = activos financieros; min = mineros; inm = bienes (terreno + auto); deu = pasivos; pat = patrimonio neto; capT/capP = capital neto (valor inicial + flujos acumulados); rend_* = rendimiento ponderado en el tiempo desde la primera fecha de la serie.","por_fecha":out,"costo_posiciones_abiertas":COST,"mineria":mineria},ensure_ascii=False,indent=1))
