# gen_customer_graph_bulk.py
import json
import random
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

# ----------------------------
# Domain models
# ----------------------------
@dataclass
class Customer:
    id: str
    name: str
    segment: str
    owner: str
    products_adopted: List[str]
    satisfaction_score: float
    health: str
    growth_potential: str
    current_arr: int
    current_mrr: int
    timezone: str
    notes: str = ""

@dataclass
class Contract:
    id: str
    customer_id: str
    start_date: str
    end_date: str
    amount: int
    status: str
    auto_renew: bool
    renewal_term_months: int
    last_renewal_date: str | None
    next_renewal_date: str | None

@dataclass
class SupportCase:
    id: str
    customer_id: str
    opened_at: str
    last_updated_at: str
    status: str
    priority: str
    escalation_level: int
    sla_breached: bool
    product_area: str
    subject: str
    tags: List[str] = field(default_factory=list)

@dataclass
class Communication:
    id: str
    customer_id: str
    timestamp: str
    channel: str
    counterpart: str
    direction: str
    sentiment: float
    summary: str

@dataclass
class Opportunity:
    id: str
    customer_id: str
    opp_type: str
    product: str
    stage: str
    amount: int
    opened_at: str
    expected_close: str

@dataclass
class TelemetryPoint:
    customer_id: str
    month: str
    dau: int
    mau: int
    feature_adoption: Dict[str, float]
    usage_hours: float
    incidents: int

@dataclass
class QBRArtifact:
    customer_id: str
    report_period: str
    highlights: List[str]
    risks: List[str]
    asks: List[str]
    attachments: List[Dict[str, str]]

# ----------------------------
# Helpers
# ----------------------------
PRODUCTS = ["Core", "Analytics", "Automation", "AI Assist", "Integrations", "Product Z"]
FEATURES = ["Dashboards", "Workflows", "API", "SSO", "Audits", "Alerts", "Copilot", "Z-Optimizer"]
SEGMENTS = ["Enterprise", "Mid-market", "SMB"]
OWNERS = ["Alex Green", "Sam Rivera", "Jordan Lee", "Taylor Kim", "Morgan Chen"]
SUBJECTS = ["API rate limits","SSO integration","Workflow stuck in pending","Analytics export timeout",
            "Unexpected logout","Alert noise tuning","Copilot hallucination","Billing discrepancy"]
AREAS = ["API","SSO","Workflows","Analytics","Auth","Alerts","Copilot","Billing"]

def iso_date(dt: datetime) -> str: return dt.strftime("%Y-%m-%d")
def months_back(n: int) -> List[datetime]:
    base = datetime.utcnow()
    y, m = base.year, base.month
    out=[]
    for _ in range(n):
        out.append(datetime(y, m, 1))
        m -= 1
        if m == 0: m, y = 12, y-1
    return list(reversed(out))
def quarter_str(dt: datetime) -> str: return f"{dt.year}-Q{(dt.month-1)//3+1}"
def bounded(v: float, lo: float, hi: float) -> float: return max(lo, min(hi, v))
def rnd(r: random.Random, a: int, b: int) -> int: return r.randint(a, b)
def jprops(d: Dict[str, Any]) -> str: return json.dumps(d, separators=(",", ":"))

def multinomial_counts(r: random.Random, total: int, buckets: int) -> List[int]:
    """Random non-negative integers summing to 'total' across 'buckets'."""
    if buckets <= 0: return []
    if total <= 0: return [0]*buckets
    cuts = sorted(r.sample(range(1, total + buckets), buckets - 1))
    parts = []
    last = 0
    nums = [c - last - 1 for c in cuts + [total + buckets]]
    # scale to match total
    # nums sum to total (since we distributed 'total' with separators)
    return nums

# ----------------------------
# Generators
# ----------------------------
def gen_customers(r: random.Random, n_customers: int) -> List[Customer]:
    out=[]
    for i in range(n_customers):
        cid = f"cust_{i+1:03d}"
        name = f"Customer {i+1:03d}"
        seg = r.choices(SEGMENTS, weights=[4,3,3])[0]
        adopted = r.sample(PRODUCTS[:-1], k=r.randint(1, 4))
        if i % 7 == 0: adopted = list(set(adopted + ["Analytics","AI Assist"]))  # some stronger adopters
        if i % 11 == 0: adopted = list(set(adopted + ["Automation"]))
        sat = round(bounded(r.normalvariate(76, 13), 35, 98), 1)
        health = "Green" if sat>=75 else ("Yellow" if sat>=55 else "Red")
        growth = r.choices(["High","Medium","Low"], weights=[4,3,2])[0]
        arr = rnd(r, 50_000, 2_000_000) if seg!="SMB" else rnd(r, 10_000, 200_000)
        out.append(Customer(
            id=cid, name=name, segment=seg, owner=r.choice(OWNERS),
            products_adopted=sorted(set(adopted)), satisfaction_score=sat,
            health=health, growth_potential=growth, current_arr=arr, current_mrr=arr//12,
            timezone=r.choice(["America/Los_Angeles","America/New_York","Europe/London","Asia/Singapore"]),
            notes="Key design partner" if i % 15 == 0 else ""
        ))
    return out

def gen_contracts(r: random.Random, cs: List[Customer]) -> List[Contract]:
    out=[]; today=datetime.utcnow()
    for c in cs:
        start = today - timedelta(days=365*2 + rnd(r,0,120))
        term = r.choice([12,12,12,24])
        end = start + timedelta(days=int(30*term))
        status = "Active"
        if end < today - timedelta(days=30): status="Expired"
        elif end < today + timedelta(days=45): status="Pending-Renewal"
        last = start + timedelta(days=365) if term>=12 else None
        next_r = end if status!="Expired" else None
        out.append(Contract(
            id=f"ctr_{c.id}", customer_id=c.id, start_date=iso_date(start), end_date=iso_date(end),
            amount=int(c.current_arr), status=status, auto_renew=r.random()<0.6,
            renewal_term_months=term, last_renewal_date=iso_date(last) if last else None,
            next_renewal_date=iso_date(next_r) if next_r else None
        ))
    return out

def gen_support_cases(r: random.Random, cs: List[Customer], total_cases: int) -> List[SupportCase]:
    # distribute total_cases across customers
    per = multinomial_counts(r, total_cases, len(cs))
    out=[]; now=datetime.utcnow()
    for c, k in zip(cs, per):
        for i in range(k):
            opened = now - timedelta(days=rnd(r,0,330))
            status = r.choices(["Open","Pending","Resolved","Closed"], weights=[1,2,4,3])[0]
            if r.random()<0.18: status=r.choice(["Open","Pending"])  # ensure some outstanding
            prio = r.choices(["P1","P2","P3"], weights=[1,3,6])[0]
            escal = 0
            if prio=="P1" and r.random()<0.45: escal = r.choice([1,2,3])
            breach = (prio=="P1" and status in ("Open","Pending") and r.random()<0.28)
            pa = r.choice(AREAS); subj = r.choice(SUBJECTS)
            out.append(SupportCase(
                id=f"case_{c.id}_{i+1}", customer_id=c.id, opened_at=iso_date(opened),
                last_updated_at=iso_date(opened+timedelta(days=rnd(r,0,30))),
                status=status, priority=prio, escalation_level=escal,
                sla_breached=breach, product_area=pa, subject=subj,
                tags=[pa.lower(), subj.split()[0].lower()]
            ))
    return out

def gen_comms(r: random.Random, cs: List[Customer], total_comms: int) -> List[Communication]:
    channels=["email","call","slack","ticket"]; personas=["CTO","VP Eng","Support Lead","PM","Admin"]
    pos=["Appreciate the quick turnaround on the fix.","The new dashboards look great.","Renewal looks good—please share updated terms."]
    neg=["Still waiting on the SSO patch.","We're seeing repeated timeouts in analytics.","Escalating this issue to our leadership."]
    per = multinomial_counts(r, total_comms, len(cs))
    out=[]; now=datetime.utcnow()
    for c, k in zip(cs, per):
        for i in range(k):
            ts = now - timedelta(days=rnd(r,0,90))
            base = r.normalvariate(0.1, 0.35)
            if r.random()<0.15: base -= 0.25
            if r.random()<0.15: base += 0.25
            sent = round(bounded(base, -1, 1), 2)
            text = r.choice(pos+neg)
            out.append(Communication(
                id=f"comm_{c.id}_{i+1}", customer_id=c.id, timestamp=ts.isoformat(timespec="seconds")+"Z",
                channel=r.choice(channels), counterpart=r.choice(personas), direction=r.choice(["inbound","outbound"]),
                sentiment=sent, summary=text
            ))
    return out

def gen_opportunities(r: random.Random, cs: List[Customer], total_opps: int) -> List[Opportunity]:
    stages=["Prospect","Qualified","Proposal","Negotiation","Closed-Won","Closed-Lost"]
    per = multinomial_counts(r, total_opps, len(cs))
    out=[]; base=datetime.utcnow()
    for c, k in zip(cs, per):
        for i in range(k):
            opened = base - timedelta(days=rnd(r,0,120)); exp = opened + timedelta(days=rnd(r,20,80))
            opp_type=r.choice(["Upsell","Cross-sell"]); product=r.choice(PRODUCTS)
            stage=r.choices(stages, weights=[3,3,2,2,2,2])[0]
            out.append(Opportunity(
                id=f"opp_{c.id}_{i+1}", customer_id=c.id, opp_type=opp_type, product=product, stage=stage,
                amount=rnd(r,5_000,150_000), opened_at=iso_date(opened), expected_close=iso_date(exp)
            ))
    return out

def gen_telemetry(r: random.Random, cs: List[Customer], months:int=12) -> List[TelemetryPoint]:
    out=[]; mlist=months_back(months)
    for c in cs:
        base_mau={"Enterprise":1200,"Mid-market":350,"SMB":80}[c.segment]
        base_dau=int(base_mau*0.35); usage=float(base_mau)*8.0
        trend = r.uniform(0.98, 1.05)
        cur_mau,cur_dau,cur_usage=base_mau,base_dau,usage
        for mdt in mlist:
            feat={}
            for f in FEATURES:
                base=r.uniform(0.05,0.85)
                if f=="Z-Optimizer": base*=r.uniform(0.2,0.6)
                if f=="Copilot" and "AI Assist" in c.products_adopted: base=min(0.95, base+0.2)
                feat[f]=round(bounded(base,0.02,0.98),2)
            incidents=rnd(r,0,3)
            out.append(TelemetryPoint(
                customer_id=c.id, month=mdt.strftime("%Y-%m"),
                dau=max(15, int(cur_dau + r.normalvariate(0, cur_dau*0.06))),
                mau=max(30, int(cur_mau + r.normalvariate(0, cur_mau*0.08))),
                feature_adoption=feat, usage_hours=round(max(5.0, cur_usage + r.normalvariate(0, cur_usage*0.05)),1),
                incidents=incidents
            ))
            cur_mau*=trend; cur_dau*=trend; cur_usage*=trend
    return out

def gen_qbr_artifacts(r: random.Random, cs: List[Customer]) -> List[QBRArtifact]:
    out=[]; period=quarter_str(datetime.utcnow())
    for c in cs:
        risks=[]
        if c.health!="Green": risks.append("Account health below target; action plan in place.")
        out.append(QBRArtifact(
            customer_id=c.id, report_period=period,
            highlights=["Expanded usage in Workflows","Adopted SSO across business units","MTTR down 18%"],
            risks=risks or ["No critical risks identified."],
            asks=["Align on next-phase roadmap","Approval for pilot of Product Z","Introduce us to data governance lead"],
            attachments=[{"type":"brief","title":f"{c.name} QBR Brief","path":f"/qbr/{c.id}_{period}.pdf"}]
        ))
    return out

# ----------------------------
# Graph conversion
# ----------------------------
def make_nodes_and_edges(
    customers: List[Customer],
    contracts: List[Contract],
    cases: List[SupportCase],
    comms: List[Communication],
    opps: List[Opportunity],
    telemetry: List[TelemetryPoint],
    qbrs: List[QBRArtifact],
) -> Tuple[List[Dict[str,str]], List[Dict[str,str]]]:
    nodes: List[Dict[str,str]] = []
    edges: List[Dict[str,str]] = []

    def add_node(_id: str, label: str, props: Dict[str,Any]):
        nodes.append({"id":_id,"label":label,"properties":jprops(props),"kind":"\"node\"","src":"","dst":""})
    def add_edge(_id: str, label: str, src: str, dst: str, props: Dict[str,Any] | None=None):
        edges.append({"id":_id,"label":label,"properties":jprops(props or {}),"kind":"\"edge\"","src":src,"dst":dst})

    # Catalogs
    product_ids = {p: f"prod_{p.lower().replace(' ','_')}" for p in PRODUCTS}
    feature_ids = {f: f"feat_{f.lower().replace(' ','_').replace('-','_')}" for f in FEATURES}
    for p, pid in product_ids.items(): add_node(pid, "Product", {"name": p})
    for f, fid in feature_ids.items(): add_node(fid, "Feature", {"name": f})

    # Customers + ADOPTED_PRODUCT
    for c in customers:
        add_node(c.id, "Customer", {
            "name": c.name, "segment": c.segment, "owner": c.owner,
            "health": c.health, "growth_potential": c.growth_potential,
            "current_arr": c.current_arr, "current_mrr": c.current_mrr,
            "satisfaction_score": c.satisfaction_score, "timezone": c.timezone, "notes": c.notes
        })
        for p in c.products_adopted:
            add_edge(f"edge_{c.id}_prod_{p}", "ADOPTED_PRODUCT", c.id, product_ids[p])

    # Contracts
    for ctr in contracts:
        add_node(ctr.id, "Contract", asdict(ctr))
        add_edge(f"edge_{ctr.customer_id}_{ctr.id}", "HAS_CONTRACT", ctr.customer_id, ctr.id)

    # Support cases (+ ABOUT_AREA)
    for sc in cases:
        add_node(sc.id, "SupportCase", asdict(sc))
        add_edge(f"edge_{sc.customer_id}_{sc.id}", "RAISED_CASE", sc.customer_id, sc.id)
        if sc.product_area in feature_ids:
            add_edge(f"edge_{sc.id}_about_{sc.product_area}", "ABOUT_AREA", sc.id, feature_ids[sc.product_area])

    # Communications
    for cm in comms:
        add_node(cm.id, "Communication", asdict(cm))
        add_edge(f"edge_{cm.customer_id}_{cm.id}", "HAD_COMM", cm.customer_id, cm.id)

    # Opportunities (+ FOR_PRODUCT)
    for op in opps:
        add_node(op.id, "Opportunity", asdict(op))
        add_edge(f"edge_{op.customer_id}_{op.id}", "HAS_OPPORTUNITY", op.customer_id, op.id)
        add_edge(f"edge_{op.id}_for_{op.product}", "FOR_PRODUCT", op.id, f"prod_{op.product.lower().replace(' ','_')}")

    # Telemetry (+ ADOPTED_FEATURE perc for key features)
    for tp in telemetry:
        tid = f"tel_{tp.customer_id}_{tp.month}"
        add_node(tid, "TelemetryMonth", asdict(tp))
        add_edge(f"edge_{tp.customer_id}_{tid}", "HAS_TELEMETRY", tp.customer_id, tid)
        for f in ("Z-Optimizer","Copilot","API"):
            if f in tp.feature_adoption:
                add_edge(f"edge_{tid}_feat_{f}", "ADOPTED_FEATURE", tid, feature_ids[f],
                         {"percent": tp.feature_adoption[f], "month": tp.month})

    # QBR artifacts
    for qb in qbrs:
        qid = f"qbr_{qb.customer_id}_{qb.report_period}"
        add_node(qid, "QBRArtifact", asdict(qb))
        add_edge(f"edge_{qb.customer_id}_{qid}", "HAS_QBR", qb.customer_id, qid)

    return nodes, edges

# ----------------------------
# CLI
# ----------------------------
def main():
    ap = argparse.ArgumentParser(description="Generate customer graph dataset at scale.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--customers", type=int, default=100)
    ap.add_argument("--opportunities", type=int, default=2000)
    ap.add_argument("--communications", type=int, default=1000)
    ap.add_argument("--support_cases", type=int, default=1500)  # “appropriate” default
    ap.add_argument("--telemetry_months_per_customer", type=int, default=12)
    ap.add_argument("--outdir", type=Path, default=Path("./data"))
    args = ap.parse_args()

    r = random.Random(args.seed)

    customers = gen_customers(r, args.customers)
    contracts = gen_contracts(r, customers)
    cases = gen_support_cases(r, customers, args.support_cases)
    comms = gen_comms(r, customers, args.communications)
    opps = gen_opportunities(r, customers, args.opportunities)
    telemetry = gen_telemetry(r, customers, months=args.telemetry_months_per_customer)
    qbrs = gen_qbr_artifacts(r, customers)

    nodes, edges = make_nodes_and_edges(customers, contracts, cases, comms, opps, telemetry, qbrs)

    args.outdir.mkdir(parents=True, exist_ok=True)

    def dump(name: str, obj: Any):
        p = args.outdir / f"{name}.json"
        with p.open("w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        print(f"Wrote {p}")

    # Domain files
    dump("customers", [asdict(x) for x in customers])
    dump("contracts", [asdict(x) for x in contracts])
    dump("support_cases", [asdict(x) for x in cases])
    dump("communications", [asdict(x) for x in comms])
    dump("opportunities", [asdict(x) for x in opps])
    dump("telemetry", [asdict(x) for x in telemetry])
    dump("qbr_artifacts", [asdict(x) for x in qbrs])

    # Graph outputs in your schema
    dump("graph_nodes", nodes)
    dump("graph_edges", edges)
    dump("graph", {"nodes": nodes, "edges": edges})

if __name__ == "__main__":
    main()
