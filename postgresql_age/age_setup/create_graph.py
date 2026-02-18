#!/usr/bin/env python3
"""
Populate a demo customer 360 graph on PostgreSQL + Apache AGE and run example queries.

- Creates extension AGE (if needed)
- Creates graph: corp_graph
- Loads synthetic data for customers, products, contracts, Jira, SharePoint, emails, Word docs, telemetry (Confluent/Kafka)
- Demonstrates openCypher queries answering 6 real-world questions

Run:
  export PGHOST=localhost PGPORT=5432 PGDATABASE=postgres PGUSER=postgres PGPASSWORD=postgres
  python demo_age_c360.py
"""

import os
import sys
import textwrap
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DSN = dict(
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5432")),
    dbname=os.getenv("PGDATABASE", "postgres"),
    user=os.getenv("PGUSER", "postgres"),
    password=os.getenv("PGPASSWORD", "postgres"),
)

GRAPH = "corp_graph"

# ---------------------------
# Helpers
# ---------------------------

def connect():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = True
    return conn

def clear_failed_txn(cur):
    # Safely clear a failed transaction, regardless of autocommit mode
    try:
        if not cur.connection.autocommit:
            cur.connection.rollback()
    except Exception:
        # If autocommit=True, rollback() raises; ignore in that case
        pass

def exec_sql(cur, sql, quiet=False):
    try:
        if not quiet:
            print("\nSQL>", sql.strip().splitlines()[0], "...")
        cur.execute(sql)
    except Exception as e:
        # clear failed txn if autocommit is off for any reason
        if not cur.connection.autocommit:
            cur.connection.rollback()
        raise

def exec_sql(cur, sql, quiet=False):
    try:
        if not quiet:
            print("\nSQL>", sql.strip().splitlines()[0], "...")
        cur.execute(sql)
    except Exception as e:
        # clear failed txn if autocommit is off for any reason
        if not cur.connection.autocommit:
            cur.connection.rollback()
        raise

def cypher(cur, graph, cypher_query, cols=("v ag_catalog.agtype",), quiet=False):
    sql = f"""
    SELECT * FROM ag_catalog.cypher('{graph}'::name, $${cypher_query}$$)
      AS ({', '.join(cols)});
    """
    try:
        if not quiet:
            print("\nCYPHER>\n", cypher_query)
        cur.execute(sql)
        return cur.fetchall()
    except Exception as e:
        if not cur.connection.autocommit:
            cur.connection.rollback()
        raise



def cypher(cur, graph, cypher_query, cols=("v ag_catalog.agtype",), quiet=False):
    sql = f"""
    SELECT * FROM ag_catalog.cypher('{graph}'::name, $${cypher_query}$$)
      AS ({', '.join(cols)});
    """
    if not quiet:
        print("\nCYPHER>\n", cypher_query)
    cur.execute(sql)
    return cur.fetchall()



def pretty(rows, headers=None, max_width=96):
    if not rows:
        print("(no rows)")
        return
    # Convert agtype payloads to strings
    str_rows = []
    for r in rows:
        str_rows.append([str(x) if x is not None else "" for x in r])

    if headers is None:
        headers = [f"col{i+1}" for i in range(len(str_rows[0]))]

    widths = [max(len(h), *(len(r[i]) for r in str_rows)) for i, h in enumerate(headers)]
    widths = [min(w, max_width) for w in widths]

    def fmt_row(vals):
        clipped = [v if len(v) <= w else v[: w - 1] + "…" for v, w in zip(vals, widths)]
        return " | ".join(v.ljust(w) for v, w in zip(clipped, widths))

    print(fmt_row(headers))
    print("-+-".join("-" * w for w in widths))
    for r in str_rows:
        print(fmt_row(r))

# ---------------------------
# Bootstrap AGE & graph
# ---------------------------

def init_age(cur):
    # Load AGE extension and set search_path
    #try:
    #    exec_sql(cur, "CREATE EXTENSION IF NOT EXISTS age;")
    #except Exception as e:
    #    print("Note: You might need SUPERUSER or to add `shared_preload_libraries='age'` in postgresql.conf.")
    #    raise

    #exec_sql(cur, "LOAD 'age';", quiet=True)
    #exec_sql(cur, "SET search_path = ag_catalog, \"$user\", public;", quiet=True)

    # Recreate graph for a fresh run
    #try:
    #    exec_sql(cur, f"SELECT drop_graph('{GRAPH}', true);", quiet=True)
    #except Exception:
    #    pass

    try:
        exec_sql(cur, f"SELECT ag_catalog.create_graph('{GRAPH}'::name);")
    except Exception as e:
        print(f"ERROR: Could not create graph. {e}")
        raise

# ---------------------------
# Data model & load
# ---------------------------

def load_demo(cur):
    # Customers, Products, Accounts, Contracts, Opportunities, Cases, Jira, SharePoint, Emails, Docs, Telemetry
    # We use UNWIND to batch inserts.

    # Customers
    cypher(cur, GRAPH, """
    UNWIND [
      {name:'Acme Corp',       segment:'Enterprise', csm:'Ava Li',   nps:42, health:'amber'},
      {name:'BrightBee',       segment:'Mid-Market', csm:'Ben Ortiz', nps:60, health:'green'},
      {name:'Cascade Retail',  segment:'Enterprise', csm:'Maya Chen', nps:18, health:'red'},
      {name:'DeltaSoft',       segment:'SMB',         csm:'Tom Reed',  nps:55, health:'green'}
    ] AS c
    CREATE (:Customer {name:c.name, segment:c.segment, csm:c.csm, nps:c.nps, health:c.health})
    RETURN 'ok'
    """, cols=("customer ag_catalog.agtype","arr ag_catalog.agtype","sla ag_catalog.agtype"), quiet=True)

    # Products
    cypher(cur, GRAPH, """
    UNWIND [
      {name:'Product Alpha',  family:'Core',    is_flagship:true},
      {name:'Product Beta',   family:'Add-on',  is_flagship:false},
      {name:'Product Zeta',   family:'AI',      is_flagship:true}
    ] AS p
    CREATE (:Product {name:p.name, family:p.family, is_flagship:p.is_flagship})
    RETURN 'ok'
    """, cols=("customer ag_catalog.agtype","arr ag_catalog.agtype","sla ag_catalog.agtype"), quiet=True)

    # Contracts (with revenue & renewal)
    cypher(cur, GRAPH, """
    UNWIND [
      {cust:'Acme Corp',       arr:1200000, renewal:'2026-03-01', sla:'Gold'},
      {cust:'BrightBee',       arr:350000,  renewal:'2026-01-15', sla:'Silver'},
      {cust:'Cascade Retail',  arr:860000,  renewal:'2025-12-01', sla:'Gold'},
      {cust:'DeltaSoft',       arr:120000,  renewal:'2026-06-20', sla:'Bronze'}
    ] AS k
    MATCH (c:Customer {name:k.cust})
    CREATE (ct:Contract {arr:k.arr, renewal_date:k.renewal, sla_tier:k.sla})
    CREATE (c)-[:HAS_CONTRACT]->(ct)
    RETURN 'ok'
    """, cols=("customer ag_catalog.agtype","arr ag_catalog.agtype","sla ag_catalog.agtype"), quiet=True)

    # Adoption / usage (via TelemetrySnapshot nodes; think Kafka-derived aggregates)
    cypher(cur, GRAPH, """
    UNWIND [
      {cust:'Acme Corp',      product:'Product Alpha',  mau:4200,  daily_events:180000, feature_adoption:['SSO','SLA','AI Assist']},
      {cust:'Acme Corp',      product:'Product Zeta',   mau:1100,  daily_events: 65000, feature_adoption:['Summarize','Forecast']},
      {cust:'BrightBee',      product:'Product Alpha',  mau:900,   daily_events: 21000, feature_adoption:['SSO']},
      {cust:'Cascade Retail', product:'Product Alpha',  mau:1200,  daily_events: 52000, feature_adoption:['SLA']},
      {cust:'DeltaSoft',      product:'Product Beta',   mau:150,   daily_events:  4000, feature_adoption:[]}
    ] AS t
    MATCH (c:Customer {name:t.cust})
    MATCH (p:Product {name:t.product})
    CREATE (snap:TelemetrySnapshot {mau:t.mau, daily_events:t.daily_events, feature_adoption:t.feature_adoption, as_of:'2025-10-01'})
    CREATE (c)-[:USES]->(p)
    CREATE (c)-[:HAS_TELEMETRY]->(snap)
    CREATE (p)-[:HAS_TELEMETRY]->(snap)
    RETURN 'ok'
    """, cols=("customer ag_catalog.agtype","arr ag_catalog.agtype","sla ag_catalog.agtype"), quiet=True)

    # Opportunities (upsell/cross-sell)
    cypher(cur, GRAPH, """
    UNWIND [
      {cust:'Acme Corp',       type:'Upsell',  product:'Product Zeta', amount:300000, stage:'Proposal',  close_prob:0.65},
      {cust:'BrightBee',       type:'Cross',   product:'Product Beta', amount: 80000, stage:'Discovery', close_prob:0.40},
      {cust:'Cascade Retail',  type:'Upsell',  product:'Product Zeta', amount:200000, stage:'Negotiate', close_prob:0.35}
    ] AS o
    MATCH (c:Customer {name:o.cust})
    MATCH (p:Product {name:o.product})
    CREATE (opp:Opportunity {type:o.type, amount:o.amount, stage:o.stage, close_prob:o.close_prob})
    CREATE (c)-[:HAS_OPPORTUNITY]->(opp)
    CREATE (opp)-[:FOR_PRODUCT]->(p)
    RETURN 'ok'
    """, cols=("customer ag_catalog.agtype","arr ag_catalog.agtype","sla ag_catalog.agtype"), quiet=True)

    # Support Cases (open/pending/escalated)
    cypher(cur, GRAPH, """
    UNWIND [
      {cust:'Acme Corp',       id:'AC-1042', severity:'P2', status:'Open',       sla_breach:false, title:'Integration error in data pipeline'},
      {cust:'BrightBee',       id:'BB-201',  severity:'P3', status:'Pending',    sla_breach:false, title:'UI latency in analytics'},
      {cust:'Cascade Retail',  id:'CR-77',   severity:'P1', status:'Escalated',  sla_breach:true,  title:'Authentication failures during peak'},
      {cust:'Cascade Retail',  id:'CR-93',   severity:'P2', status:'Open',       sla_breach:false, title:'Export job stuck in queue'}
    ] AS s
    MATCH (c:Customer {name:s.cust})
    CREATE (cs:Case {case_id:s.id, severity:s.severity, status:s.status, sla_breach:s.sla_breach, title:s.title})
    CREATE (c)-[:HAS_CASE]->(cs)
    RETURN 'ok'
    """, cols=("customer ag_catalog.agtype","arr ag_catalog.agtype","sla ag_catalog.agtype"), quiet=True)

    # Jira Issues linked to cases / product work
    cypher(cur, GRAPH, """
    UNWIND [
      {key:'ENG-1456', title:'Fix auth spike',        status:'In Progress', priority:'High',  relates_case:'CR-77'},
      {key:'ENG-1499', title:'Analytics perf tweak',  status:'Done',        priority:'Med',  relates_case:'BB-201'},
      {key:'ENG-1520', title:'Connector retry logic', status:'Backlog',     priority:'High', relates_case:'AC-1042'}
    ] AS j
    MATCH (cs:Case {case_id:j.relates_case})
    CREATE (ji:Jira {key:j.key, title:j.title, status:j.status, priority:j.priority})
    CREATE (ji)-[:RELATES_TO]->(cs)
    RETURN 'ok'
    """, cols=("customer ag_catalog.agtype","arr ag_catalog.agtype","sla ag_catalog.agtype"), quiet=True)

    # SharePoint team sites + Word docs
    cypher(cur, GRAPH, """
    UNWIND [
      {site:'SP/Acme/Account',       doc:'Acme_QBR_2025-09.docx',     doc_type:'QBR',   summary:'Q4 plan; AI adoption; risks: auth'},
      {site:'SP/BrightBee/Account',  doc:'BrightBee_Renewal.docx',    doc_type:'MSA',   summary:'Renewal terms; 2yr; add Beta trial'},
      {site:'SP/Cascade/Support',    doc:'Cascade_RCA_Auth.docx',     doc_type:'RCA',   summary:'Root cause auth spikes; mitigations'}
    ] AS s
    CREATE (site:SharePointSite {path:s.site})
    CREATE (doc:WordDoc {name:s.doc, doc_type:s.doc_type, summary:s.summary})
    CREATE (site)-[:HAS_DOC]->(doc)
    WITH s, doc
    MATCH (c:Customer {name: CASE WHEN s.site STARTS WITH 'SP/Acme' THEN 'Acme Corp'
                                  WHEN s.site STARTS WITH 'SP/BrightBee' THEN 'BrightBee'
                                  ELSE 'Cascade Retail' END })
    CREATE (c)-[:HAS_DOC]->(doc)
    RETURN 'ok'
    """, cols=("customer ag_catalog.agtype","arr ag_catalog.agtype","sla ag_catalog.agtype"), quiet=True)

    # Emails (M365) with simplistic sentiment and topic
    cypher(cur, GRAPH, """
    UNWIND [
      {cust:'Acme Corp',       subj:'Re: Proposal next steps',            sentiment:'positive',   date:'2025-10-10', topic:'Sales'},
      {cust:'Acme Corp',       subj:'Escalation follow-up on pipeline',   sentiment:'neutral',    date:'2025-09-28', topic:'Support'},
      {cust:'BrightBee',       subj:'Trial request for Beta add-on',      sentiment:'positive',   date:'2025-09-30', topic:'Sales'},
      {cust:'Cascade Retail',  subj:'Urgent: SLA breach confirmation',    sentiment:'negative',   date:'2025-10-02', topic:'Support'},
      {cust:'Cascade Retail',  subj:'QBR prep - risks and mitigations',  sentiment:'negative',   date:'2025-10-05', topic:'QBR'}
    ] AS m
    MATCH (c:Customer {name:m.cust})
    CREATE (e:Email {subject:m.subj, sentiment:m.sentiment, date:m.date, topic:m.topic})
    CREATE (c)-[:HAS_COMM]->(e)
    RETURN 'ok'
    """, cols=("customer ag_catalog.agtype","arr ag_catalog.agtype","sla ag_catalog.agtype"), quiet=True)

# ---------------------------
# Example Queries (the 6 asks)
# ---------------------------

def q1_customer_insight(cur, customer):
    print(f"\n1) Consolidated insight for sales call — {customer}")
    # Revenue (ARR)
    rows = cypher(cur, GRAPH, f"""
    MATCH (c:Customer {{name:'{customer}'}})-[:HAS_CONTRACT]->(ct:Contract)
    RETURN c.name AS customer, ct.arr AS arr, ct.sla_tier AS sla
    """, cols=("customer agtype", "arr agtype", "sla agtype"))
    pretty(rows, ["customer","ARR","SLA"])

    # Pending/Open cases
    rows = cypher(cur, GRAPH, f"""
    MATCH (:Customer {{name:'{customer}'}})-[:HAS_CASE]->(cs:Case)
    WHERE cs.status IN ['Open','Pending','Escalated']
    RETURN cs.case_id, cs.severity, cs.status, cs.sla_breach, cs.title
    """, cols=("case_id agtype","severity agtype","status agtype","sla_breach agtype","title agtype"))
    print("\nOpen/Pending/Escalated cases:")
    pretty(rows, ["case_id","severity","status","sla_breach","title"])

    # Opportunities
    rows = cypher(cur, GRAPH, f"""
    MATCH (:Customer {{name:'{customer}'}})-[:HAS_OPPORTUNITY]->(o:Opportunity)-[:FOR_PRODUCT]->(p:Product)
    RETURN o.type, p.name AS product, o.amount, o.stage, o.close_prob
    """, cols=("type agtype","product agtype","amount agtype","stage agtype","close_prob agtype"))
    print("\nActive opportunities:")
    pretty(rows, ["type","product","amount","stage","close_prob"])

    # Recent comms + sentiment (last ~45 days)
    rows = cypher(cur, GRAPH, f"""
    MATCH (:Customer {{name:'{customer}'}})-[:HAS_COMM]->(e:Email)
    WHERE e.date >= '2025-08-28'
    RETURN e.date, e.topic, e.subject, e.sentiment
    ORDER BY e.date DESC
    """, cols=("date agtype","topic agtype","subject agtype","sentiment agtype"))
    print("\nRecent comms (last ~45 days) + sentiment:")
    pretty(rows, ["date","topic","subject","sentiment"])

def q2_journey_last_12m(cur, customer):
    print(f"\n2) 12-month journey — {customer}")
    # Contract renewals inside 12m window (synthetic; we just list current)
    rows = cypher(cur, GRAPH, f"""
    MATCH (:Customer {{name:'{customer}'}})-[:HAS_CONTRACT]->(ct:Contract)
    RETURN ct.renewal_date, ct.sla_tier
    """, cols=("renewal_date agtype","sla_tier agtype"))
    print("\nContract snapshots:")
    pretty(rows, ["renewal_date","sla_tier"])

    # Support escalations
    rows = cypher(cur, GRAPH, f"""
    MATCH (:Customer {{name:'{customer}'}})-[:HAS_CASE]->(cs:Case)
    WHERE cs.status = 'Escalated'
    OPTIONAL MATCH (ji:Jira)-[:RELATES_TO]->(cs)
    RETURN cs.case_id, cs.severity, cs.title, cs.sla_breach, collect(ji.key) AS jira_links
    """, cols=("case_id agtype","severity agtype","title agtype","sla_breach agtype","jira_links agtype"))
    print("\nEscalations (with linked Jira):")
    pretty(rows, ["case_id","severity","title","sla_breach","jira_links"])

    # Feature adoption trends (just the latest telemetry snapshot here)
    rows = cypher(cur, GRAPH, f"""
    MATCH (:Customer {{name:'{customer}'}})-[:HAS_TELEMETRY]->(t:TelemetrySnapshot)
    RETURN t.as_of, t.mau, t.daily_events, t.feature_adoption
    ORDER BY t.as_of DESC
    """, cols=("as_of agtype","mau agtype","daily_events agtype","feature_adoption agtype"))
    print("\nTelemetry snapshots (latest first):")
    pretty(rows, ["as_of","MAU","daily_events","features"])

    # Satisfaction signals (NPS + last 45d email sentiment)
    rows = cypher(cur, GRAPH, f"""
    MATCH (c:Customer {{name:'{customer}'}})
    OPTIONAL MATCH (c)-[:HAS_COMM]->(e:Email)
    WHERE e.date >= '2025-08-28'
    RETURN c.nps, c.health, collect(e.sentiment) AS recent_sentiments
    """, cols=("nps agtype","health agtype","recent_sentiments agtype"))
    print("\nSatisfaction signals:")
    pretty(rows, ["NPS","health","recent_sentiments"])

def q3_key_risks(cur, customer):
    print(f"\n3) Key risks — {customer}")
    # SLA breaches, recurring escalations, churn signals (low MAU trend proxy via low MAU)
    rows = cypher(cur, GRAPH, f"""
    MATCH (c:Customer {{name:'{customer}'}})
    OPTIONAL MATCH (c)-[:HAS_CASE]->(cs:Case)
    WITH c, collect(cs) AS cases
    OPTIONAL MATCH (c)-[:HAS_TELEMETRY]->(t:TelemetrySnapshot)
    WITH c, cases, max(t.mau) AS max_mau
    RETURN c.name, 
           [x IN cases WHERE x.sla_breach = true | x.case_id] AS sla_breaches,
           [x IN cases WHERE x.status = 'Escalated' | x.case_id] AS escalations,
           (CASE WHEN coalesce(max_mau,0) < 500 THEN true ELSE false END) AS churn_signal
    """, cols=("name agtype","sla_breaches agtype","escalations agtype","churn_signal agtype"))
    pretty(rows, ["customer","sla_breaches","escalations","churn_signal"])

def q4_compare(cur, a, b):
    print(f"\n4) Compare customers — {a} vs {b}")
    for cust in (a, b):
        rows = cypher(cur, GRAPH, f"""
        MATCH (c:Customer {{name:'{cust}'}})
        OPTIONAL MATCH (c)-[:HAS_CONTRACT]->(ct:Contract)
        OPTIONAL MATCH (c)-[:HAS_TELEMETRY]->(t:TelemetrySnapshot)
        OPTIONAL MATCH (c)-[:HAS_OPPORTUNITY]->(o:Opportunity)
        RETURN c.name, coalesce(ct.arr,0) AS arr, max(t.mau) AS mau, sum(coalesce(o.amount,0)) AS pipeline, c.health
        """, cols=("name agtype","arr agtype","mau agtype","pipeline agtype","health agtype"))
        pretty(rows, ["customer","ARR","MAU","pipeline","health"])

def q5_who_benefits_from_product(cur, product_name):
    print(f"\n5) Which customers are likely to benefit from {product_name}?")
    # Heuristic: customers with related cases & linked Jira + existing usage signals for adjacent features but without product adoption
    rows = cypher(cur, GRAPH, f"""
    MATCH (c:Customer)
    OPTIONAL MATCH (c)-[:USES]->(pWanted:Product {{name:'{product_name}'}})
    WITH c, count(pWanted) AS already_uses
    OPTIONAL MATCH (c)-[:HAS_TELEMETRY]->(t:TelemetrySnapshot)
    OPTIONAL MATCH (c)-[:HAS_CASE]->(cs:Case)
    WITH c, already_uses, max(t.mau) AS mau, count(cs) AS case_count,
         sum(CASE WHEN cs.status='Escalated' THEN 1 ELSE 0 END) AS escalations
    WHERE already_uses = 0  // exclude current adopters
    RETURN c.name, mau, case_count, escalations,
           (CASE WHEN (mau > 800 AND escalations >= 1) OR (mau > 1000 AND case_count >= 1)
                 THEN 'High Fit'
                 WHEN mau > 300 THEN 'Medium Fit'
                 ELSE 'Low Fit' END) AS fit
    ORDER BY fit DESC, mau DESC
    """, cols=("name agtype","mau agtype","case_count agtype","escalations agtype","fit agtype"))
    pretty(rows, ["customer","MAU","cases","escalations","fit"])

def q6_qbr_summary(cur, customer):
    print(f"\n6) Executive-ready QBR summary — {customer}")
    # Pull from contracts, support, account docs, comms (subjects), opportunities, and telemetry
    rows = cypher(cur, GRAPH, f"""
    MATCH (c:Customer {{name:'{customer}'}})
    OPTIONAL MATCH (c)-[:HAS_CONTRACT]->(ct:Contract)
    OPTIONAL MATCH (c)-[:HAS_CASE]->(cs:Case)
    OPTIONAL MATCH (c)-[:HAS_DOC]->(d:WordDoc)
    OPTIONAL MATCH (c)-[:HAS_COMM]->(e:Email)
    OPTIONAL MATCH (c)-[:HAS_OPPORTUNITY]->(o:Opportunity)
    OPTIONAL MATCH (c)-[:HAS_TELEMETRY]->(t:TelemetrySnapshot)
    RETURN c.name,
           coalesce(ct.arr,0) AS arr,
           ct.renewal_date,
           collect(DISTINCT d.name) AS key_docs,
           [x IN collect(DISTINCT e) | x.subject][0..5] AS recent_subjects,
           sum(coalesce(o.amount,0)) AS pipeline,
           max(t.mau) AS mau,
           c.health
    """, cols=("name agtype","arr agtype","renewal_date agtype","key_docs agtype","recent_subjects agtype","pipeline agtype","mau agtype","health agtype"))
    pretty(rows, ["customer","ARR","renewal","key_docs","recent_emails","pipeline","MAU","health"])

# ---------------------------
# Main
# ---------------------------

def main():
    print("Connecting to PostgreSQL with AGE…")
    with connect() as conn, conn.cursor() as cur:
        clear_failed_txn(cur)
        init_age(cur)
        print("Loading demo data…")
        load_demo(cur)

        # Run the 6 example query sets
        q1_customer_insight(cur, "Acme Corp")
        q2_journey_last_12m(cur, "Acme Corp")
        q3_key_risks(cur, "Cascade Retail")
        q4_compare(cur, "Acme Corp", "BrightBee")
        q5_who_benefits_from_product(cur, "Product Zeta")
        q6_qbr_summary(cur, "Cascade Retail")

        print("\nDone.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nERROR:", e)
        sys.exit(1)
