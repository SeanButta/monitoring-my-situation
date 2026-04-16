#!/usr/bin/env python3
import os, glob, json, subprocess, hashlib, re, time
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import uvicorn

app = FastAPI()
PASSWORD      = "midwest2026"
SESSION_TOKEN = hashlib.sha256(PASSWORD.encode()).hexdigest()
HERMES   = Path.home() / ".hermes"
REPORTS  = Path.home() / "reports"
CONTENT  = Path.home() / "content" / "drafts"
PROFILES = HERMES / "profiles"
SHARED   = Path("/shared-memory")
LEADS_RAW = Path.home() / "leads" / "raw"
LEADS_ENR = Path.home() / "leads" / "enriched"
OUTREACH  = Path.home() / "outreach" / "ready"
AGENTS = ["coordinator","designer","developer","devops","growth","product","researcher","sales","strategist"]
AGENT_META = {
    "coordinator":("Coordinator","Routes tasks · delegates · synthesizes"),
    "growth":     ("Growth","GTM · content · outreach · SEO"),
    "strategist": ("Strategist","Competitive intel · positioning"),
    "developer":  ("Developer","Build · code · debug · ship"),
    "devops":     ("DevOps","Deploy · infra · security · cron"),
    "designer":   ("Designer","UI/UX · brand · specs"),
    "sales":      ("Sales","Pipeline · outreach · close"),
    "researcher": ("Researcher","Deep research · data · analysis"),
    "product":    ("Product","PRDs · roadmap · specs"),
}
_cache = {}
def cached(key,fn,ttl=60):
    now=time.time()
    if key in _cache and now-_cache[key][0]<ttl: return _cache[key][1]
    result=fn(); _cache[key]=(now,result); return result
def rf(path,n=4000):
    try: return Path(path).read_text()[:n]
    except: return ""
def fmt_dt(iso):
    try: return datetime.fromisoformat(iso).strftime("%b %d · %H:%M")
    except: return str(iso)[:16] if iso else "—"
def dur(s,e):
    try:
        d=int((datetime.fromisoformat(e)-datetime.fromisoformat(s)).total_seconds()/60)
        return f"{d}m" if d<60 else f"{d//60}h {d%60}m"
    except: return "—"
def get_cron_jobs():
    def _f():
        try:
            r=subprocess.run(["/root/.local/bin/hermes","cron","list"],capture_output=True,text=True,timeout=8)
            jobs,cur=[],{}
            for line in r.stdout.splitlines():
                s=line.strip()
                m=re.match(r"([a-f0-9]{12})\s+\[(active|paused)\]",s)
                if m:
                    if cur.get("id"): jobs.append(cur)
                    cur={"id":m.group(1),"status":m.group(2)}
                elif s.startswith("Name:"): cur["name"]=s.split("Name:",1)[1].strip()
                elif s.startswith("Schedule:"): cur["schedule"]=s.split("Schedule:",1)[1].strip()
                elif s.startswith("Next run:"):
                    raw=s.split("Next run:",1)[1].strip()
                    try: cur["next"]=datetime.fromisoformat(raw).strftime("%b %d · %H:%M UTC")
                    except: cur["next"]=raw
                elif s.startswith("Deliver:"): cur["deliver"]=s.split("Deliver:",1)[1].strip()
            if cur.get("id"): jobs.append(cur)
            return jobs
        except: return []
    return cached("crons",_f,ttl=120)
def get_sessions(agent,limit=20):
    sdir=PROFILES/agent/"sessions"; out=[]
    for f in sorted(sdir.glob("session_*.json"),reverse=True)[:limit]:
        try:
            d=json.loads(f.read_text())
            out.append({"session_id":d.get("session_id",""),"platform":d.get("platform",""),
                "duration":dur(d.get("session_start",""),d.get("last_updated","")),"fmt_start":fmt_dt(d.get("session_start",""))})
        except: pass
    return out
def get_session_messages(agent,sid):
    fu=la=None
    def parse(msgs):
        nonlocal fu,la
        for msg in msgs:
            try:
                role=msg.get("role",""); c=msg.get("content","")
                if isinstance(c,list): c=" ".join(b.get("text","") for b in c if isinstance(b,dict))
                c=str(c or "").strip()
                if not c or c.startswith("[SYSTEM:"): continue
                if role=="user" and not fu: fu=c[:600]
                if role=="assistant" and c: la=c[:800]
            except: pass
    for name in [f"session_{sid}.json",f"{sid}.json"]:
        p=PROFILES/agent/"sessions"/name
        if p.exists():
            try:
                d=json.loads(p.read_text()); msgs=d.get("messages",[])
                if msgs: parse(msgs); break
            except: pass
    if not fu and not la:
        p=PROFILES/agent/"sessions"/f"{sid}.jsonl"
        if p.exists():
            try:
                for line in p.read_text().splitlines():
                    if line.strip():
                        try: parse([json.loads(line)])
                        except: pass
            except: pass
    return fu,la
def get_activity_feed(limit=20):
    def _f():
        feed=[]
        for agent in AGENTS:
            label=AGENT_META[agent][0]; sdir=PROFILES/agent/"sessions"
            if not sdir.exists(): continue
            for f in sdir.glob("session_*.json"):
                try:
                    d=json.loads(f.read_text())
                    feed.append({"agent":agent,"label":label,"platform":d.get("platform",""),
                        "end":d.get("last_updated",""),"fmt":fmt_dt(d.get("last_updated","")),
                        "duration":dur(d.get("session_start",""),d.get("last_updated","")),"session_id":d.get("session_id","")})
                except: pass
        feed.sort(key=lambda x:x.get("end",""),reverse=True); return feed[:limit]
    return cached("activity",_f,ttl=30)
def get_agent_data(name):
    profile=PROFILES/name; soul=rf(profile/"SOUL.md",3000); packs,sc=[],0
    sd=profile/"skills"
    if sd.exists():
        for d in sorted(sd.iterdir()):
            if not d.is_dir() or d.name.startswith("."): continue
            cnt=len(list(d.rglob("SKILL.md"))); sc+=cnt; desc=""
            df=d/"DESCRIPTION.md"
            if df.exists():
                m2=re.search(r'description:\s*(.+)',df.read_text()[:300])
                if m2: desc=m2.group(1).strip()[:80]
            subs=[s.name for s in sorted(d.iterdir()) if s.is_dir() and not s.name.startswith(".")]
            packs.append({"name":d.name,"count":cnt,"desc":desc,"subs":subs})
    return {"soul":soul,"packs":packs,"skill_count":sc,"sessions":get_sessions(name)}
def get_shared_sections():
    text=rf(SHARED/"RESEARCH.md",6000)
    if not text or len(text.strip())<20: return []
    sections,cur_h,cur_l=[],"Notes",[]
    for line in text.splitlines():
        if line.startswith("## "):
            if cur_l: sections.append({"h":cur_h,"lines":[l for l in cur_l if l.strip()]})
            cur_h,cur_l=line[3:].strip(),[]
        elif line.strip() and not line.startswith("#"): cur_l.append(line.strip())
    if cur_l: sections.append({"h":cur_h,"lines":[l for l in cur_l if l.strip()]})
    return [s for s in sections if s["lines"]]
def get_reports(folder="competitors"):
    rows=[]
    for f in sorted(glob.glob(str(REPORTS/folder/"*.md")),reverse=True):
        p=Path(f); rows.append({"name":p.name,"size":f"{p.stat().st_size}b","date":fmt_dt(datetime.fromtimestamp(p.stat().st_mtime).isoformat())})
    return rows[:10]
def get_briefings():
    rows=[]
    for f in sorted(glob.glob(str(Path.home()/"reports"/"briefings"/"*.md")),reverse=True):
        p=Path(f); rows.append({"name":p.name,"stem":p.stem,"size":f"{p.stat().st_size}b"})
    return rows[:10]
def get_content_drafts():
    rows=[]
    try:
        for f in sorted(glob.glob(str(CONTENT/"*.md")),reverse=True):
            p=Path(f); rows.append({"name":p.name,"date":fmt_dt(datetime.fromtimestamp(p.stat().st_mtime).isoformat())})
    except: pass
    return rows[:10]
def get_leads_today():
    today=datetime.now().strftime("%Y-%m-%d"); rows=[]
    for folder,label in [(LEADS_ENR,"enriched"),(LEADS_RAW,"raw")]:
        f=folder/f"{today}.md"
        if f.exists(): rows.append({"name":f.name,"folder":label,"size":f"{f.stat().st_size}b","date":today})
    for f in sorted(glob.glob(str(LEADS_ENR/"*.md")),reverse=True)[:5]:
        p=Path(f)
        if p.stem!=today: rows.append({"name":p.name,"folder":"enriched","size":f"{p.stat().st_size}b","date":p.stem})
    return rows[:8]
def get_outreach_files():
    rows=[]
    for f in sorted(glob.glob(str(OUTREACH/"*.md")),reverse=True):
        p=Path(f); rows.append({"name":p.name,"size":f"{p.stat().st_size}b","date":fmt_dt(datetime.fromtimestamp(p.stat().st_mtime).isoformat())})
    return rows[:10]
def get_outreach_content(filename):
    filename=filename.replace("/","").replace("..","")
    p=OUTREACH/filename
    if not p.exists(): return []
    text=p.read_text(); blocks=[]; current={}
    for line in text.splitlines():
        if line.startswith("## "):
            if current.get("company"): blocks.append(current)
            current={"company":line[3:].strip(),"lines":[]}
        elif current: current["lines"].append(line)
    if current.get("company"): blocks.append(current)
    result=[]
    for b in blocks:
        linkedin=""; email_subject=""; email_body=""; pain=""; in_li=False; in_em=False
        for line in b["lines"]:
            if "Pain:" in line: pain=line.split(":",1)[-1].strip().lstrip("*").strip()
            elif "LinkedIn DM" in line: in_li=True; in_em=False
            elif "### Email" in line or "**Email**" in line: in_li=False; in_em=True
            elif "Subject:" in line and in_em: email_subject=line.split("Subject:",1)[-1].strip()
            elif in_li and line.strip() and not line.startswith("#") and not line.startswith("**"): linkedin+=line+" "
            elif in_em and line.strip() and "Subject:" not in line and not line.startswith("#") and not line.startswith("**"): email_body+=line+"\n"
        result.append({"company":b["company"],"pain":pain,"linkedin":linkedin.strip(),"email_subject":email_subject,"email_body":email_body.strip()})
    return result
def get_memory():
    text=rf(HERMES/"memories"/"MEMORY.md")
    return [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#") and len(l.strip())>10][:8]
def total_sessions():
    return cached("ts",lambda:sum(len(list((PROFILES/a/"sessions").glob("session_*.json"))) for a in AGENTS if (PROFILES/a/"sessions").exists()),ttl=60)
def total_skills():
    return cached("tk",lambda:sum(len(list((PROFILES/a/"skills").rglob("SKILL.md"))) for a in AGENTS if (PROFILES/a/"skills").exists()),ttl=300)
def is_authed(s=None): return s==SESSION_TOKEN

@app.get("/login",response_class=HTMLResponse)
async def login_page(): return HTMLResponse(LOGIN_HTML)
@app.post("/login")
async def do_login(request:Request):
    form=await request.form()
    if form.get("password")==PASSWORD:
        resp=RedirectResponse("/",status_code=302)
        resp.set_cookie("session",SESSION_TOKEN,max_age=86400*30,httponly=True)
        return resp
    return HTMLResponse(LOGIN_HTML.replace("</form>",'<p class="err">Wrong password.</p></form>'))
@app.get("/logout")
async def logout():
    resp=RedirectResponse("/login",status_code=302); resp.delete_cookie("session"); return resp
@app.get("/api/agent/{name}")
async def api_agent(name:str,session:str=Cookie(default=None)):
    if not is_authed(session): return JSONResponse({"error":"unauthorized"},status_code=401)
    if name not in AGENTS: return JSONResponse({"error":"not found"},status_code=404)
    return JSONResponse(get_agent_data(name))
@app.get("/api/session/{agent}/{sid}")
async def api_session(agent:str,sid:str,session:str=Cookie(default=None)):
    if not is_authed(session): return JSONResponse({"error":"unauthorized"},status_code=401)
    first,last=get_session_messages(agent,sid)
    return JSONResponse({"first_user":first,"last_assistant":last})
@app.get("/api/file/{folder}/{filename}")
async def api_file(folder:str,filename:str,session:str=Cookie(default=None)):
    if not is_authed(session): return JSONResponse({"error":"unauthorized"},status_code=401)
    filename=filename.replace("/","").replace("..",""); folder=folder.replace("/","").replace("..","")
    for p in [Path.home()/"reports"/folder/filename,Path.home()/"reports"/"briefings"/filename,
              Path.home()/"reports"/"competitors"/filename,Path.home()/"content"/"drafts"/filename,
              Path.home()/"leads"/"enriched"/filename,Path.home()/"leads"/"raw"/filename,
              Path.home()/"outreach"/"ready"/filename,SHARED/filename]:
        if p.exists(): return JSONResponse({"content":p.read_text()[:12000],"name":filename})
    return JSONResponse({"error":"not found"},status_code=404)
@app.get("/api/outreach/{filename}")
async def api_outreach(filename:str,session:str=Cookie(default=None)):
    if not is_authed(session): return JSONResponse({"error":"unauthorized"},status_code=401)
    return JSONResponse({"blocks":get_outreach_content(filename),"filename":filename})
@app.get("/",response_class=HTMLResponse)
async def root(session:str=Cookie(default=None)):
    return RedirectResponse("/page/agents")
@app.get("/page/{page}",response_class=HTMLResponse)
async def page_view(page:str,session:str=Cookie(default=None)):
    if not is_authed(session): return RedirectResponse("/login")
    return HTMLResponse(_build_page(page,datetime.utcnow().strftime("%a %b %d %Y · %H:%M UTC")))

def _build_page(page,now):
    crons=get_cron_jobs(); activity=get_activity_feed(); ts=total_sessions(); tk=total_skills()
    def co(title,badge="",bcls="chip-n"):
        b=f'<span class="chip {bcls}">{badge}</span>' if badge else ""
        return f'<div class="card"><div class="ch"><span class="ct">{title}</span>{b}</div>'
    cc="</div>"
    def metrics(*items):
        h=f'<div class="metrics" style="grid-template-columns:repeat({len(items)},minmax(0,1fr))">'
        for label,val,cls,sub in items:
            h+=f'<div class="met"><div class="mlabel">{label}</div><div class="mvalue {cls}">{val}</div><div class="msub">{sub}</div></div>'
        return h+"</div>"
    def agent_grid():
        h='<div class="agent-grid">'
        for name,(label,desc) in AGENT_META.items():
            sdir=PROFILES/name/"sessions"; nsess=len(list(sdir.glob("session_*.json"))) if sdir.exists() else 0
            status="online"; dot="dot-g"
            if name=="designer" and nsess<2: status="idle"; dot="dot-a"
            chip="chip-g" if status=="online" else "chip-a"
            h+=f'<div class="agent-card" onclick="openAgent(\'{name}\')"><div class="ac-row"><div><div class="aname"><span class="dot {dot}"></span>{label}</div><div class="adesc">{desc}</div></div><div style="text-align:right"><span class="chip {chip}">{status}</span><div class="sc">{nsess} sess</div></div></div></div>'
        return h+"</div>"
    def activity_rows(limit=15):
        if not activity: return '<div class="empty">No sessions yet.</div>'
        h=""
        for s in activity[:limit]:
            src="chip-b" if s["platform"]=="telegram" else "chip-n"
            h+=f'<div class="drow clickable" onclick="openSession(\'{s["agent"]}\',\'{s["session_id"]}\')"><div><div class="rt"><span class="dot dot-g" style="margin-right:5px"></span>{s["label"]}</div><div class="rm">{s["fmt"]} · {s["duration"]}</div></div><span class="chip {src}">{s["platform"] or "cron"}</span></div>'
        return h
    def cron_rows():
        if not crons: return '<div class="empty">No cron jobs configured.</div>'
        return "".join(f'<div class="drow"><div><div class="rt"><span class="dot dot-g" style="margin-right:5px"></span>{j.get("name","—")}</div><div class="rm">Next: {j.get("next","—")} · {j.get("deliver","—")}</div></div><code class="mono-chip">{j.get("schedule","—")}</code></div>' for j in crons)
    def file_rows(items,folder="competitors"):
        if not items: return '<div class="empty">No files yet.</div>'
        h=""
        for r in items:
            n=r["name"]; d=r.get("date",r.get("stem","")); s=r.get("size",""); f=r.get("folder",folder)
            h+=f'<div class="drow clickable" onclick="openFile(\'{f}\',\'{n}\')"><div><div class="rt">{n}</div><div class="rm">{s} · {d}</div></div><span class="chip chip-b">read →</span></div>'
        return h
    def shared_html():
        secs=get_shared_sections()
        if not secs: return '<div class="empty">Agents write here 6-7am daily. Check back after scans run.</div>'
        h=""
        for s in secs:
            h+=f'<div class="sec-label">{s["h"]}</div>'
            for line in s["lines"][:6]: h+=f'<div class="mline">{line}</div>'
        return h
    def memory_rows():
        mem=get_memory()
        if not mem: return '<div class="empty">Auto-populates after cron runs.</div>'
        return "".join(f'<div class="mline">{m}</div>' for m in mem)

    if page=="agents":
        body=metrics(("Agents","9","g","all profiles active"),("Sessions",str(ts),"","across all agents"),("Skills",str(tk),"","total across agents"),("Cron jobs",str(len(crons)),"","active"))
        body+=agent_grid()
        body+='<div class="g2">'+co("Recent activity — click any run to inspect",f"{ts} total","chip-g")+activity_rows()+cc+'<div class="col">'+co("Cron schedule",f"{len(crons)} active","chip-g")+cron_rows()+cc+co("Memory snapshot","MEMORY.md")+memory_rows()+cc+"</div></div>"
        title,sub="Agent dashboard",f"9 agents · {ts} sessions · Hermes Codex 5.3"
    elif page=="briefing":
        briefings=get_briefings()
        body=metrics(("Briefings",str(len(briefings)),"g","saved to disk"),("Next run","7:30am","","coordinator"),("Source agents","4","","researcher · strategist · growth · sales"),("Delivery","telegram","","+ disk"))
        body+='<div class="g2">'+co("Briefing archive — click to read","daily · 7:30am","chip-g")+file_rows(briefings,"briefings")+cc
        body+=co("Pipeline","coordinator")+'<div class="mline">6:00am — Researcher: market shifts</div><div class="mline">6:20am — Strategist: competitor intel</div><div class="mline">6:40am — Growth: content angles</div><div class="mline">7:00am — Sales: lead signals</div><div class="mline">7:30am — Coordinator synthesizes all four to Telegram and disk</div>'+cc+"</div>"
        title,sub="Morning briefing","daily intel · coordinator · 7:30am UTC"
    elif page=="market":
        secs=get_shared_sections()
        body=metrics(("Sections today",str(len(secs)),"g" if secs else "","live in /shared-memory/"),("Next scan","6:00am","","researcher"),("Topics","4","","market · comp · content · leads"),("API","Exa","","neural search"))
        body+=co("Today's agent research","live" if secs else "empty","chip-g" if secs else "chip-n")+shared_html()+cc
        title,sub="Market research","daily scans · 6-7am UTC · Exa neural search"
    elif page=="competitors":
        comp=get_reports("competitors")
        body=metrics(("Reports",str(len(comp)),"g","on disk"),("Next scrape","Mon 8am","","GTM Monday Intel"),("Tracking","8 competitors","","2-week rotation"),("Exa cost","~$0.02/run","","months of runway"))
        body+=co("Competitor reports — click to read","Midwest","chip-b")+file_rows(comp,"competitors")+cc
        body+='<div class="g2" style="margin-top:.75rem">'+co("Group A — odd weeks")+'<div class="mline">Pluriza — AI intelligence for SMBs</div><div class="mline">IRIS IQ — governance-first agents</div><div class="mline">SmallForce — AI workforce for small biz</div><div class="mline">Lindy — AI assistant SMB pricing</div>'+cc
        body+=co("Group B — even weeks")+'<div class="mline">Andron — AI workflow automation</div><div class="mline">Flow Automations — $99/$299 realtor ICP</div><div class="mline">Automiq AI — SMB automation</div><div class="mline">Arahi AI — SMB automation</div>'+cc+"</div>"
        title,sub="Competitor intel","8 SMB competitors · 2-week rotation · Monday 8am"
    elif page=="content":
        drafts=get_content_drafts()
        body=metrics(("Drafts",str(len(drafts)),"a" if drafts else "","~/content/drafts/"),("Next drop","Fri 8am","","GTM Friday"),("Formats","3","","LinkedIn · Twitter · Blog"),("Agent","Growth","","drafts to review"))
        body+=co("Content drafts — click to read","Friday · growth","chip-g")+file_rows(drafts,"drafts")+cc
        body+='<div style="margin-top:.75rem">'+co("Pipeline")+'<div class="mline">Friday 8am — Growth scans trending SMB topics via Exa</div><div class="mline">Reads Monday comp report for positioning angles</div><div class="mline">Drafts 3 LinkedIn hooks + 2 Twitter openers + 1 blog idea</div><div class="mline">Saves to ~/content/drafts/YYYY-MM-DD-hooks.md</div>'+cc+"</div>"
        title,sub="Content angles","weekly drafts · Friday 8am · growth agent"
    elif page=="leads":
        leads=get_leads_today(); outreach_files=get_outreach_files()
        today=datetime.now().strftime("%Y-%m-%d")
        raw_today=LEADS_RAW/f"{today}.md"
        lead_count=raw_today.read_text().count("## ") if raw_today.exists() else 0
        body=metrics(("Leads today",str(lead_count),"g" if lead_count else "","~/leads/raw/"),("Outreach ready",str(len(outreach_files)),"a" if outreach_files else "","~/outreach/ready/"),("Next scan","6:00am","","sales agent"),("Radius","200mi","","from Kenosha WI"))
        body+='<div class="g2">'
        body+=co("Lead files — click to read",f"{len(leads)} files","chip-g" if leads else "chip-n")
        body+=(file_rows(leads,"enriched") if leads else '<div class="empty">No leads yet. First scan runs at 6am.</div>')+cc
        body+=co("Outreach drafts — click to open","growth · 6:40am","chip-b")
        if outreach_files:
            for r in outreach_files:
                n=r["name"]
                body+=f'<div class="drow clickable" onclick="openOutreach(\'{n}\')"><div><div class="rt">{n}</div><div class="rm">{r["size"]} · {r["date"]}</div></div><span class="chip chip-b">open →</span></div>'
        else:
            body+='<div class="empty">No outreach drafts yet. Runs at 6:40am daily.</div>'
        body+=cc+"</div>"
        body+=co("What sales agent looks for")+'<div class="mline">Landscapers, HVAC, plumbers, contractors, remodelers within 200mi of Kenosha WI</div><div class="mline">Signals: admin overwhelm posts · ops/admin job postings · scaling pain mentions</div><div class="mline">Output: company · location · signal · pain-first LinkedIn DM + email draft</div>'+cc
        title,sub="Leads and Outreach","daily scan · sales agent · 6am UTC · ContractorOS $129/mo"
    elif page=="midwest":
        comp=get_reports("competitors"); drafts=get_content_drafts(); outreach_files=get_outreach_files(); leads=get_leads_today()
        body=metrics(("Comp reports",str(len(comp)),"g","on disk"),("Outreach ready",str(len(outreach_files)),"a" if outreach_files else "","ready to send"),("Content drafts",str(len(drafts)),"","~/content/drafts/"),("Price","$129/mo","g","service businesses"))
        body+='<div class="g2">'+co("Outreach drafts","growth · 6:40am","chip-b")
        if outreach_files:
            for r in outreach_files[:4]:
                n=r["name"]; body+=f'<div class="drow clickable" onclick="openOutreach(\'{n}\')"><div class="rt">{n}</div><span class="chip chip-b">open →</span></div>'
        else:
            body+='<div class="empty">No outreach drafts yet.</div>'
        body+=cc+co("Lead files","sales · 6am","chip-g")+file_rows(leads,"enriched")+cc+"</div>"
        body+='<div class="g2">'+co("Competitor reports","strategist · Monday","chip-b")+file_rows(comp[:4],"competitors")+cc+co("Content drafts","growth · Friday","chip-g")+file_rows(drafts[:4],"drafts")+cc+"</div>"
        body+=co("ICP and positioning")+'<div class="mline">Product: ContractorOS — CRM + invoicing + vendor mgmt + reporting · web app · $129/mo</div><div class="mline">ICP: Landscapers, HVAC, plumbers, contractors, remodelers · under 50 employees · Midwest first</div><div class="mline">Outreach: pain-first LinkedIn DM under 280 chars · email fallback · never mention AI first</div><div class="mline">Anti-SaaS angle: replaces QuickBooks + Jobber + CRM ($180+/mo fragmented) with one platform</div>'+cc
        title,sub="Midwest Workflow Co.","ContractorOS · $129/mo · service businesses · Kenosha + Midwest"
    elif page=="dockside":
        body=metrics(("Season","pre-season","a","Kenosha · Racine"),("Agent config","pending","","not set up"),("Outreach cron","pending","","not configured"),("Booking data","pending","","not tracked"))
        body+='<div class="g2">'+co("Marina status")+'<div class="drow"><div class="rt">Kenosha marina</div><span class="chip chip-n">not tracked</span></div><div class="drow"><div class="rt">Racine marina</div><span class="chip chip-n">not tracked</span></div><div class="drow"><div class="rt">Season outreach cron</div><span class="chip chip-n">pending</span></div><div class="drow"><div class="rt">Booking pipeline</div><span class="chip chip-n">pending</span></div>'+cc
        body+=co("Setup checklist")+'<div class="mline">1. Create Dockside agent profile in Hermes</div><div class="mline">2. Configure marina season outreach cron</div><div class="mline">3. Connect booking data from docksideboatcare.com/admin</div><div class="mline">4. Set up marine detailing competitor pricing scan</div><div class="mline">5. Wire revenue data to this dashboard</div>'+cc+"</div>"
        title,sub="Dockside Boat Care","mobile marine detailing · Kenosha and Racine"
    elif page=="crons":
        body=metrics(("Active jobs",str(len(crons)),"g","all running"),("Daily scans","5","","6-7:30am UTC"),("Weekly intel","2","","Mon + Fri"),("Delivery","telegram","","morning briefing"))
        body+=co(f"All scheduled jobs",f"{len(crons)} active","chip-g")+cron_rows()+cc
        body+='<div style="margin-top:.75rem">'+co("Schedule overview")+'<div class="mline">6:00am daily  — Market scan + Lead scan</div><div class="mline">6:20am daily  — Competitive scan + Lead enrichment</div><div class="mline">6:40am daily  — Content scan + Outreach drafts</div><div class="mline">7:30am daily  — Morning briefing to Telegram + disk</div><div class="mline">8:00am Monday — GTM deep scrape</div><div class="mline">8:00am Friday — Content batch</div>'+cc+"</div>"
        title,sub="Cron schedule",f"{len(crons)} active jobs · Hermes scheduler"
    elif page=="skills":
        packs=[]
        sd=HERMES/"skills"
        if sd.exists():
            for d in sorted(sd.iterdir()):
                if d.is_dir() and not d.name.startswith("."):
                    subs=[s.name for s in sorted(d.iterdir()) if s.is_dir() and not s.name.startswith(".")]
                    packs.append({"name":d.name,"count":len(subs) or len(list(d.glob("*.md")))})
        gtm=list((HERMES/"skills"/"gtm").glob("*.md")) if (HERMES/"skills"/"gtm").exists() else []
        body=metrics(("Total skills",str(tk),"g","across agents"),("Custom GTM",str(len(gtm)),"g","~/.hermes/skills/gtm/"),("Packs",str(len(packs)),"","community + custom"),("Agents","9","","each inherits all"))
        body+='<div class="g2">'+co("Custom GTM skills","~/.hermes/skills/gtm/","chip-g")
        body+=("".join(f'<div class="drow"><div class="rt">{f.name}</div><span class="chip chip-g">active</span></div>' for f in sorted(gtm))) if gtm else '<div class="empty">No custom GTM skills.</div>'
        body+=cc+co("Skill packs",f"{len(packs)} packs")+"".join(f'<div class="drow"><div class="rt">{p["name"]}/</div><span class="chip chip-n">{p["count"]} skills</span></div>' for p in packs)+cc+"</div>"
        title,sub="Skills library",f"{tk} total · 9 agents · ~/.hermes/skills/"
    elif page=="world":
        body=metrics(("Status","disabled","a","re-enabling soon"),("Plan","Codex + Exa","","markets · geo · SMB/AI"),("Timing","5:30am UTC","","before agent scans"),("Delivery","dashboard","","no Telegram"))
        body+=co("World briefing — coming soon")+'<div class="mline">Will scan: S&P 500 · crypto · Fed signals · macro</div><div class="mline">Will scan: geopolitical developments affecting US business</div><div class="mline">Will scan: SMB + AI industry news · funding · layoffs</div><div class="mline" style="color:var(--amber)">Disabled — revisiting data sources before re-enabling</div>'+cc
        title,sub="World briefing","disabled · re-enabling with better data sources"
    else:
        body='<div class="empty">Page not found.</div>'; title,sub="404",""
    html=SHELL.replace("{{TITLE}}",title).replace("{{SUB}}",sub).replace("{{NOW}}",now).replace("{{BODY}}",body)
    for p in ["briefing","market","competitors","content","leads","world","agents","crons","skills","midwest","dockside"]:
        html=html.replace("{{"+p+"}}","active" if p==page else "")
    return html

LOGIN_HTML='<!DOCTYPE html><html><head><meta charset="utf-8"><title>Business OS</title>\n<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">\n<style>*{box-sizing:border-box;margin:0;padding:0}body{background:#0a0c10;color:#c8d0d8;font-family:"IBM Plex Sans",sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}.box{width:360px;border:1px solid #1e2530;border-radius:8px;padding:2.5rem;background:#0e1117}h1{font-family:"IBM Plex Mono",monospace;font-size:15px;color:#e8edf2;margin-bottom:.25rem}p{font-size:12px;color:#5a6476;margin-bottom:2rem}label{font-size:10px;color:#5a6476;text-transform:uppercase;letter-spacing:.08em;display:block;margin-bottom:.4rem}input{width:100%;background:#0a0c10;border:1px solid #1e2530;color:#c8d0d8;padding:.65rem .85rem;border-radius:5px;font-family:"IBM Plex Mono",monospace;font-size:14px;outline:none;margin-bottom:1.25rem}input:focus{border-color:#3d8b6e}button{width:100%;background:#1a3d2e;border:1px solid #2a6b4e;color:#4eca8e;padding:.7rem;border-radius:5px;font-family:"IBM Plex Mono",monospace;font-size:13px;cursor:pointer}.err{color:#e05555;font-size:12px;margin-bottom:.75rem}</style></head>\n<body><div class="box"><h1>BUSINESS OS</h1><p>Sean Fitzgerald - Kenosha, WI</p>\n<form method="post" action="/login"><label>Access code</label><input type="password" name="password" autofocus><button>ENTER</button></form></div></body></html>'
SHELL='<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{TITLE}} - Business OS</title><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet"><style>*{box-sizing:border-box;margin:0;padding:0}:root{--bg0:#0a0c10;--bg1:#0e1117;--bg2:#131820;--bo:#1e2530;--bo2:#2a3548;--t0:#e8edf2;--t1:#9aa5b4;--t2:#5a6476;--t3:#3a4456;--green:#4eca8e;--gd:#1a3d2e;--gb:#2a6b4e;--amber:#f0a832;--ad:#3a2a10;--ab:#6b4a1e;--blue:#5b9cf6;--bd:#162040;--bb:#2a4a8e;--mono:"IBM Plex Mono",monospace;--sans:"IBM Plex Sans",sans-serif}body{background:var(--bg0);color:var(--t1);font-family:var(--sans);font-size:13px;height:100vh;display:flex;flex-direction:column;overflow:hidden}.shell{display:flex;flex:1;overflow:hidden}.sidebar{width:210px;flex-shrink:0;background:var(--bg1);border-right:1px solid var(--bo);display:flex;flex-direction:column;overflow-y:auto}.sb-brand{padding:.85rem 1rem;border-bottom:1px solid var(--bo)}.sb-logo{font-family:var(--mono);font-size:12px;font-weight:500;color:var(--t0);display:flex;align-items:center;gap:6px}.sb-dot{width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 5px var(--green)}.sb-time{font-family:var(--mono);font-size:10px;color:var(--t3);margin-top:3px}.sb-sec{padding:.6rem 1rem .2rem;font-family:var(--mono);font-size:9px;color:var(--t3);text-transform:uppercase;letter-spacing:.1em}.sb-item{display:flex;align-items:center;gap:8px;padding:.42rem .7rem;margin:1px 5px;border-radius:5px;color:var(--t2);font-size:11px;text-decoration:none;transition:background .1s,color .1s}.sb-item:hover{background:var(--bg2);color:var(--t1)}.sb-item.active{background:rgba(78,202,142,.1);color:var(--green)}.sb-item.active .sb-ic{color:var(--green)}.sb-ic{font-size:11px;width:14px;text-align:center;color:var(--t3);flex-shrink:0}.sb-badge{margin-left:auto;font-family:var(--mono);font-size:9px;padding:1px 5px;border-radius:8px;background:rgba(78,202,142,.12);color:var(--green)}.sb-space{flex:1}.sb-foot{padding:.6rem 1rem;border-top:1px solid var(--bo);font-family:var(--mono);font-size:9px;color:var(--t3)}.main{flex:1;display:flex;flex-direction:column;overflow:hidden}.topbar{display:flex;align-items:center;justify-content:space-between;padding:.6rem 1.25rem;border-bottom:1px solid var(--bo);background:var(--bg1);flex-shrink:0}.page-title{font-family:var(--mono);font-size:13px;font-weight:500;color:var(--t0)}.page-sub{font-size:10px;color:var(--t2);margin-top:2px}.logout{font-family:var(--mono);font-size:10px;color:var(--t2);border:1px solid var(--bo);padding:3px 9px;border-radius:4px;text-decoration:none}.logout:hover{color:var(--t1)}.body{flex:1;overflow-y:auto;padding:1rem 1.25rem}.metrics{display:grid;gap:8px;margin-bottom:.9rem}.met{background:var(--bg2);border-radius:6px;padding:.7rem .85rem}.mlabel{font-family:var(--mono);font-size:9px;color:var(--t2);text-transform:uppercase;letter-spacing:.08em;margin-bottom:.25rem}.mvalue{font-size:20px;font-weight:500;color:var(--t0);font-family:var(--mono)}.mvalue.g{color:var(--green)}.mvalue.a{color:var(--amber)}.msub{font-size:10px;color:var(--t2);margin-top:.1rem}.card{background:var(--bg1);border:1px solid var(--bo);border-radius:8px;padding:.85rem 1rem;margin-bottom:.75rem}.ch{display:flex;justify-content:space-between;align-items:center;padding-bottom:.55rem;margin-bottom:.55rem;border-bottom:1px solid var(--bo)}.ct{font-family:var(--mono);font-size:9px;color:var(--t2);text-transform:uppercase;letter-spacing:.08em}.g2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:.75rem;margin-bottom:.75rem}.col{display:flex;flex-direction:column;gap:.75rem}.agent-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-bottom:.75rem}.agent-card{background:var(--bg2);border:1px solid var(--bo);border-radius:6px;padding:.6rem .75rem;cursor:pointer;transition:border-color .12s}.agent-card:hover{border-color:var(--gb)}.ac-row{display:flex;justify-content:space-between;align-items:center}.aname{font-size:12px;font-weight:500;color:var(--t0);display:flex;align-items:center;gap:5px}.adesc{font-size:10px;color:var(--t2);margin-top:2px}.sc{font-size:9px;color:var(--t2);font-family:var(--mono);margin-top:2px}.drow{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--bo)}.drow:last-child{border-bottom:none}.drow.clickable{cursor:pointer}.drow.clickable:hover .rt{color:var(--green)}.rt{font-size:11px;font-weight:500;color:var(--t0)}.rm{font-size:10px;color:var(--t2);font-family:var(--mono);margin-top:1px}.mline{font-size:11px;color:var(--t1);padding:4px 0;border-bottom:1px solid var(--bo);font-family:var(--mono);line-height:1.5}.mline:last-child{border-bottom:none}.sec-label{font-family:var(--mono);font-size:9px;color:var(--t2);text-transform:uppercase;letter-spacing:.08em;margin:.4rem 0 .2rem}.sblock{font-family:var(--mono);font-size:10px;color:var(--t1);white-space:pre-wrap;background:var(--bg0);border:1px solid var(--bo);border-radius:4px;padding:.65rem .8rem;line-height:1.8;overflow-y:auto}.empty{font-size:11px;color:var(--t2);font-style:italic;padding:.35rem 0;font-family:var(--mono)}.dot{width:5px;height:5px;border-radius:50%;display:inline-block;flex-shrink:0}.dot-g{background:var(--green);box-shadow:0 0 3px var(--green)}.dot-a{background:var(--amber)}.chip{font-family:var(--mono);font-size:9px;padding:2px 6px;border-radius:8px;border:1px solid transparent;white-space:nowrap}.chip-g{background:var(--gd);color:var(--green);border-color:var(--gb)}.chip-a{background:var(--ad);color:var(--amber);border-color:var(--ab)}.chip-n{background:var(--bg2);color:var(--t2);border-color:var(--bo)}.chip-b{background:var(--bd);color:var(--blue);border-color:var(--bb)}.mono-chip{font-family:var(--mono);font-size:9px;padding:2px 6px;border-radius:4px;background:var(--bg0);border:1px solid var(--bo2);color:var(--t2)}.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:200;align-items:flex-start;justify-content:center;padding:2rem;overflow-y:auto}.overlay.open{display:flex}.modal{background:var(--bg1);border:1px solid var(--bo2);border-radius:10px;width:100%;max-width:820px;margin:auto}.modal-sm{max-width:680px}.mhead{display:flex;justify-content:space-between;align-items:center;padding:.85rem 1.1rem;border-bottom:1px solid var(--bo)}.mtitle{font-family:var(--mono);font-size:13px;font-weight:500;color:var(--t0)}.mclose{background:none;border:1px solid var(--bo);color:var(--t2);font-family:var(--mono);font-size:11px;padding:3px 9px;border-radius:4px;cursor:pointer}.mclose:hover{color:var(--t0)}.mbody{padding:1.1rem;max-height:78vh;overflow-y:auto}.msec{margin-bottom:1.1rem}.msec-title{font-family:var(--mono);font-size:9px;color:var(--t2);text-transform:uppercase;letter-spacing:.08em;margin-bottom:.35rem;padding-bottom:.3rem;border-bottom:1px solid var(--bo)}.sess-row{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--bo);cursor:pointer}.sess-row:last-child{border-bottom:none}.sess-row:hover .sess-name{color:var(--green)}.sess-name{font-size:11px;font-family:var(--mono);color:var(--t0)}.sess-meta{font-size:10px;color:var(--t2)}.sess-exp{background:var(--bg0);border:1px solid var(--bo);border-radius:4px;padding:.6rem;margin:4px 0;display:none}.sess-exp.open{display:block}.pack-row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--bo)}.pack-row:last-child{border-bottom:none}.pack-name{font-size:11px;font-family:var(--mono);color:var(--t0)}.pack-desc{font-size:10px;color:var(--t2)}.pack-cnt{font-size:9px;font-family:var(--mono);color:var(--green)}.pills{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px}.pill{font-size:9px;font-family:var(--mono);padding:2px 6px;border-radius:4px;background:var(--bg2);border:1px solid var(--bo2);color:var(--t2)}.loading{font-family:var(--mono);font-size:11px;color:var(--t2);padding:.75rem 0}.outreach-card{background:var(--bg2);border:1px solid var(--bo);border-radius:6px;padding:.85rem;margin-bottom:.75rem}.outreach-company{font-size:13px;font-weight:500;color:var(--t0);margin-bottom:.25rem}.outreach-pain{font-size:11px;color:var(--amber);margin-bottom:.75rem;font-family:var(--mono)}.outreach-section{margin-bottom:.65rem}.outreach-label{font-size:9px;font-family:var(--mono);color:var(--t2);text-transform:uppercase;letter-spacing:.08em;margin-bottom:.3rem;display:flex;justify-content:space-between;align-items:center}.outreach-text{font-size:11px;color:var(--t1);background:var(--bg0);border:1px solid var(--bo);border-radius:4px;padding:.6rem .75rem;font-family:var(--mono);line-height:1.6;white-space:pre-wrap}.copy-btn{font-family:var(--mono);font-size:9px;padding:2px 8px;border-radius:4px;border:1px solid var(--gb);background:var(--gd);color:var(--green);cursor:pointer}.copy-btn:hover{background:#1f4a38}.copy-btn.copied{border-color:var(--amber);background:var(--ad);color:var(--amber)}</style></head><body><div class="shell"><nav class="sidebar"><div class="sb-brand"><div class="sb-logo"><span class="sb-dot"></span>BUSINESS OS</div><div class="sb-time">{{NOW}}</div></div><div class="sb-sec">Intelligence</div><a href="/page/briefing" class="sb-item {{briefing}}"><span class="sb-ic">o</span>Morning briefing<span class="sb-badge">7:30am</span></a><a href="/page/market" class="sb-item {{market}}"><span class="sb-ic">o</span>Market research</a><a href="/page/competitors" class="sb-item {{competitors}}"><span class="sb-ic">o</span>Competitor intel</a><a href="/page/content" class="sb-item {{content}}"><span class="sb-ic">o</span>Content angles</a><a href="/page/leads" class="sb-item {{leads}}"><span class="sb-ic">o</span>Leads and Outreach</a><a href="/page/world" class="sb-item {{world}}"><span class="sb-ic">o</span>World briefing</a><div class="sb-sec">Operations</div><a href="/page/agents" class="sb-item {{agents}}"><span class="sb-ic">o</span>Agent dashboard</a><a href="/page/crons" class="sb-item {{crons}}"><span class="sb-ic">o</span>Cron schedule</a><a href="/page/skills" class="sb-item {{skills}}"><span class="sb-ic">o</span>Skills library</a><div class="sb-sec">Ventures</div><a href="/page/midwest" class="sb-item {{midwest}}"><span class="sb-ic">o</span>Midwest Workflow</a><a href="/page/dockside" class="sb-item {{dockside}}"><span class="sb-ic">o</span>Dockside Boat Care</a><div class="sb-space"></div><div class="sb-foot">Hetzner FSN1 - port 8000</div></nav><div class="main"><div class="topbar"><div><div class="page-title">{{TITLE}}</div><div class="page-sub">{{SUB}}</div></div><a href="/logout" class="logout">logout</a></div><div class="body">{{BODY}}</div></div></div><div class="overlay" id="agentOv" onclick="closeBg(event,\'agentOv\')"><div class="modal"><div class="mhead"><span class="mtitle" id="agentTitle">Agent</span><button class="mclose" onclick="closeModal(\'agentOv\')">CLOSE X</button></div><div class="mbody" id="agentBody"><div class="loading">Loading...</div></div></div></div><div class="overlay" id="sessOv" onclick="closeBg(event,\'sessOv\')"><div class="modal modal-sm"><div class="mhead"><span class="mtitle" id="sessTitle">Session</span><button class="mclose" onclick="closeModal(\'sessOv\')">CLOSE X</button></div><div class="mbody" id="sessBody"><div class="loading">Loading...</div></div></div></div><div class="overlay" id="outreachOv" onclick="closeBg(event,\'outreachOv\')"><div class="modal"><div class="mhead"><span class="mtitle" id="outreachTitle">Outreach Drafts</span><button class="mclose" onclick="closeModal(\'outreachOv\')">CLOSE X</button></div><div class="mbody" id="outreachBody"><div class="loading">Loading...</div></div></div></div><script>const AL={coordinator:"Coordinator",designer:"Designer",developer:"Developer",devops:"DevOps",growth:"Growth",product:"Product",researcher:"Researcher",sales:"Sales",strategist:"Strategist"};function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}function renderMd(t){if(!t)return"";t=esc(t);t=t.replace(/^# (.+)$/gm,"<h2 style=\'color:var(--t0);margin:.5rem 0 .25rem;font-size:13px\'>$1</h2>");t=t.replace(/^## (.+)$/gm,"<h3 style=\'color:var(--green);margin:.4rem 0 .2rem;font-size:11px;text-transform:uppercase;letter-spacing:.06em\'>$1</h3>");t=t.replace(/^### (.+)$/gm,"<h4 style=\'color:var(--blue);margin:.3rem 0 .15rem;font-size:11px\'>$1</h4>");t=t.replace(/^---$/gm,"<hr style=\'border-color:var(--bo);margin:.4rem 0\'>");t=t.replace(/^[-*] (.+)$/gm,"<div style=\'padding:2px 0\'>&bull; $1</div>");t=t.replace(/\n\n/g,"<br>");return t;}async function openAgent(name){document.getElementById("agentTitle").textContent=AL[name]||name;document.getElementById("agentBody").innerHTML="<div class=\\"loading\\">Loading "+name+"...</div>";document.getElementById("agentOv").classList.add("open");try{const d=await fetch("/api/agent/"+name).then(r=>r.json());let h="<div class=\\"msec\\"><div class=\\"msec-title\\">SOUL.md</div><div class=\\"sblock\\" style=\\"max-height:220px\\">"+renderMd(d.soul||"(empty)")+"</div></div>";h+="<div class=\\"msec\\"><div class=\\"msec-title\\">Skills - "+d.skill_count+" loaded</div>";(d.packs||[]).forEach(p=>{h+="<div class=\\"pack-row\\"><div><div class=\\"pack-name\\">"+esc(p.name)+"/</div>"+(p.desc?"<div class=\\"pack-desc\\">"+esc(p.desc)+"</div>":"")+(p.subs&&p.subs.length?"<div class=\\"pills\\">"+p.subs.map(s=>"<span class=\\"pill\\">"+esc(s)+"</span>").join("")+"</div>":"")+"</div><span class=\\"pack-cnt\\">"+p.count+"</span></div>";});h+="</div><div class=\\"msec\\"><div class=\\"msec-title\\">Session history - "+(d.sessions||[]).length+" runs</div>";if(!d.sessions||!d.sessions.length){h+="<div class=\\"empty\\">No sessions yet.</div>";}else{d.sessions.forEach((s,i)=>{const sc=s.platform==="telegram"?"chip-b":"chip-n";h+="<div class=\\"sess-row\\" onclick=\\"toggleSess(\'se"+i+"\',\'"+name+"\',\'"+s.session_id+"\')\\">"+"<div><div class=\\"sess-name\\">"+esc(s.fmt_start)+"</div><div class=\\"sess-meta\\">"+esc(s.duration)+" - "+esc(s.platform||"cron")+"</div></div>"+"<span class=\\"chip "+sc+"\\">"+esc(s.platform||"cron")+"</span></div>"+"<div class=\\"sess-exp\\" id=\\"se"+i+"\\"><div class=\\"loading\\">Loading...</div></div>";});}h+="</div>";document.getElementById("agentBody").innerHTML=h;}catch(e){document.getElementById("agentBody").innerHTML="<div class=\\"empty\\">Error: "+esc(e.message)+"</div>";}}async function toggleSess(id,agent,sid){const el=document.getElementById(id);if(el.classList.contains("open")){el.classList.remove("open");return;}el.classList.add("open");if(el.dataset.loaded)return;el.dataset.loaded="1";try{const d=await fetch("/api/session/"+agent+"/"+sid).then(r=>r.json());let h="";if(d.first_user)h+="<div class=\\"msec-title\\">Task</div><div class=\\"sblock\\" style=\\"max-height:120px\\">"+esc(d.first_user)+"</div>";if(d.last_assistant)h+="<div class=\\"msec-title\\" style=\\"margin-top:.5rem\\">Result</div><div class=\\"sblock\\" style=\\"max-height:140px\\">"+esc(d.last_assistant)+"</div>";el.innerHTML=h||"<div class=\\"empty\\">Could not parse session.</div>";}catch(e){el.innerHTML="<div class=\\"empty\\">Error.</div>";}}async function openSession(agent,sid){document.getElementById("sessTitle").textContent=(AL[agent]||agent)+" - "+sid.slice(0,8);document.getElementById("sessBody").innerHTML="<div class=\\"loading\\">Loading...</div>";document.getElementById("sessOv").classList.add("open");try{const d=await fetch("/api/session/"+agent+"/"+sid).then(r=>r.json());let h="";if(d.first_user)h+="<div class=\\"msec\\"><div class=\\"msec-title\\">Task</div><div class=\\"sblock\\">"+esc(d.first_user)+"</div></div>";if(d.last_assistant)h+="<div class=\\"msec\\"><div class=\\"msec-title\\">Result</div><div class=\\"sblock\\">"+esc(d.last_assistant)+"</div></div>";document.getElementById("sessBody").innerHTML=h||"<div class=\\"empty\\">Could not parse.</div>";}catch(e){document.getElementById("sessBody").innerHTML="<div class=\\"empty\\">Error: "+esc(e.message)+"</div>";}}async function openFile(folder,filename){document.getElementById("sessTitle").textContent=filename;document.getElementById("sessBody").innerHTML="<div class=\\"loading\\">Loading...</div>";document.getElementById("sessOv").classList.add("open");try{const d=await fetch("/api/file/"+folder+"/"+encodeURIComponent(filename)).then(r=>r.json());if(d.error){document.getElementById("sessBody").innerHTML="<div class=\\"empty\\">"+esc(d.error)+"</div>";return;}document.getElementById("sessBody").innerHTML="<div class=\\"msec\\"><div class=\\"sblock\\" style=\\"max-height:65vh\\">"+renderMd(d.content)+"</div></div>";}catch(e){document.getElementById("sessBody").innerHTML="<div class=\\"empty\\">Error: "+esc(e.message)+"</div>";}}async function openOutreach(filename){document.getElementById("outreachTitle").textContent="Outreach - "+filename;document.getElementById("outreachBody").innerHTML="<div class=\\"loading\\">Loading outreach drafts...</div>";document.getElementById("outreachOv").classList.add("open");try{const d=await fetch("/api/outreach/"+encodeURIComponent(filename)).then(r=>r.json());if(!d.blocks||!d.blocks.length){const f=await fetch("/api/file/outreach%2Fready/"+encodeURIComponent(filename)).then(r=>r.json());document.getElementById("outreachBody").innerHTML="<div class=\\"msec\\"><div class=\\"sblock\\" style=\\"max-height:65vh\\">"+esc(f.content||"")+"</div></div>";return;}let h="";d.blocks.forEach((b,i)=>{h+="<div class=\\"outreach-card\\">";h+="<div class=\\"outreach-company\\">"+esc(b.company)+"</div>";if(b.pain)h+="<div class=\\"outreach-pain\\">Pain: "+esc(b.pain)+"</div>";if(b.linkedin){h+="<div class=\\"outreach-section\\"><div class=\\"outreach-label\\"><span>LinkedIn DM</span><button class=\\"copy-btn\\" onclick=\\"copyText(this,\'"+encodeURIComponent(b.linkedin)+"\')\\" >Copy</button></div><div class=\\"outreach-text\\">"+esc(b.linkedin)+"</div></div>";}if(b.email_body){const full=(b.email_subject?"Subject: "+b.email_subject+"\n\n":"")+b.email_body;h+="<div class=\\"outreach-section\\"><div class=\\"outreach-label\\"><span>Email"+(b.email_subject?" - "+esc(b.email_subject):"")+"</span><button class=\\"copy-btn\\" onclick=\\"copyText(this,\'"+encodeURIComponent(full)+"\')\\" >Copy</button></div><div class=\\"outreach-text\\">"+esc(b.email_body)+"</div></div>";}h+="</div>";});document.getElementById("outreachBody").innerHTML=h;}catch(e){document.getElementById("outreachBody").innerHTML="<div class=\\"empty\\">Error: "+esc(e.message)+"</div>";}}function copyText(btn,encoded){const text=decodeURIComponent(encoded);navigator.clipboard.writeText(text).then(()=>{btn.textContent="Copied!";btn.classList.add("copied");setTimeout(()=>{btn.textContent="Copy";btn.classList.remove("copied");},2000);});}function closeModal(id){document.getElementById(id).classList.remove("open");}function closeBg(e,id){if(e.target===document.getElementById(id))closeModal(id);}document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeModal("agentOv");closeModal("sessOv");closeModal("outreachOv");}});setTimeout(()=>location.reload(),300000);</script></body></html>'

if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=8000,log_level="warning")
