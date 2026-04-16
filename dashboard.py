#!/usr/bin/env python3
import os, glob, json, subprocess, hashlib, re
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
HERMES_BIN = "/root/.local/bin/hermes"
AGENTS   = ["coordinator","designer","developer","devops","growth","product","researcher","sales","strategist"]
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
STATUS_MAP = {
    "coordinator":("online","dot-g"),"growth":("online","dot-g"),"strategist":("online","dot-g"),
    "developer":("online","dot-g"),"devops":("online","dot-g"),"designer":("idle","dot-a"),
    "sales":("online","dot-g"),"researcher":("online","dot-g"),"product":("online","dot-g"),
}
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
    try:
        r=subprocess.run([HERMES_BIN,"cron","list"],capture_output=True,text=True,timeout=10)
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
    except Exception as ex:
        return [{"name":f"error: {ex}","schedule":"—","next":"—","deliver":"—","id":"","status":"error"}]
def get_sessions(agent,limit=20):
    sdir=PROFILES/agent/"sessions"; out=[]
    for f in sorted(sdir.glob("session_*.json"),reverse=True)[:limit]:
        try:
            d=json.loads(f.read_text())
            out.append({"session_id":d.get("session_id",""),"platform":d.get("platform",""),
                "end":d.get("last_updated",""),"duration":dur(d.get("session_start",""),d.get("last_updated","")),
                "fmt_start":fmt_dt(d.get("session_start",""))})
        except: pass
    return out
def get_session_messages(agent,sid):
    fu=la=None
    json_path=PROFILES/agent/"sessions"/f"{sid}.json"
    jsonl_path=PROFILES/agent/"sessions"/f"{sid}.jsonl"
    def parse_msgs(msgs):
        nonlocal fu,la
        for msg in msgs:
            try:
                role=msg.get("role",""); c=msg.get("content","")
                if isinstance(c,list): c=" ".join(b.get("text","") for b in c if isinstance(b,dict))
                c=str(c or "").strip()
                if not c or c.startswith("[SYSTEM:"): continue
                if role=="user" and not fu: fu=c[:500]
                if role=="assistant" and c: la=c[:700]
            except: pass
    try:
        # try with and without session_ prefix
        for path in [json_path, PROFILES/agent/"sessions"/f"session_{sid}.json"]:
            if path.exists():
                d=json.loads(path.read_text())
                msgs=d.get("messages",[])
                if msgs: parse_msgs(msgs)
                break
    except: pass
    if not fu and not la:
        try:
            for line in jsonl_path.read_text().splitlines():
                if not line.strip(): continue
                try: parse_msgs([json.loads(line)])
                except: pass
        except: pass
    return fu,la

def get_activity_feed(limit=15):
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
    feed.sort(key=lambda x:x.get("end",""),reverse=True)
    return feed[:limit]
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
    text=rf(SHARED/"RESEARCH.md",5000)
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
def get_world_reports():
    rows = []
    for f in sorted(__import__("glob").glob(str(Path.home()/"reports"/"world"/"*.md")), reverse=True):
        p = Path(f)
        rows.append({"name": p.name, "stem": p.stem, "size": f"{p.stat().st_size}b"})
    return rows[:10]

def get_leads(folder="enriched"):
    rows = []
    import glob as g
    for f in sorted(g.glob(str(Path.home()/f"leads/{folder}"/"*.md")), reverse=True):
        p = Path(f)
        rows.append({"name": p.name, "stem": p.stem, "size": f"{p.stat().st_size}b"})
    return rows[:7]

def get_outreach():
    rows = []
    import glob as g
    for f in sorted(g.glob(str(Path.home()/"outreach"/"ready"/"*.md")), reverse=True):
        p = Path(f)
        rows.append({"name": p.name, "stem": p.stem, "size": f"{p.stat().st_size}b"})
    return rows[:7]

def get_memory():
    text=rf(HERMES/"memories"/"MEMORY.md")
    return [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#") and len(l.strip())>10][:8]
def total_sessions():
    return sum(len(list((PROFILES/a/"sessions").glob("session_*.json"))) for a in AGENTS if (PROFILES/a/"sessions").exists())
def total_skills():
    t=0
    for a in AGENTS:
        sd=PROFILES/a/"skills"
        if sd.exists(): t+=len(list(sd.rglob("SKILL.md")))
    return t
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
    for p in [Path.home()/"reports"/folder/filename,Path.home()/"reports"/"briefings"/filename,Path.home()/"reports"/"world"/filename,Path.home()/"content"/"drafts"/filename,Path.home()/"leads"/"enriched"/filename,Path.home()/"leads"/"raw"/filename,Path.home()/"outreach"/"ready"/filename,SHARED/filename]:
        if p.exists(): return JSONResponse({"content":p.read_text()[:10000],"name":filename})
    return JSONResponse({"error":"not found"},status_code=404)

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
            status,dot=STATUS_MAP.get(name,("online","dot-g"))
            chip="chip-g" if status=="online" else "chip-a"
            nsess=len(list((PROFILES/name/"sessions").glob("session_*.json"))) if (PROFILES/name/"sessions").exists() else 0
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
        if not crons: return '<div class="empty">No cron jobs found.</div>'
        return "".join(f'<div class="drow"><div><div class="rt"><span class="dot dot-g" style="margin-right:5px"></span>{j.get("name","—")}</div><div class="rm">Next: {j.get("next","—")} · {j.get("deliver","—")}</div></div><code class="mono-chip">{j.get("schedule","—")}</code></div>' for j in crons)
    def file_rows(items,folder="competitors"):
        if not items: return '<div class="empty">No files yet.</div>'
        h=""
        for r in items:
            n=r["name"]; d=r.get("date",r.get("stem","")); s=r.get("size","")
            h+=f'<div class="drow clickable" onclick="openFile(\'{folder}\',\'{n}\')"><div><div class="rt">{n}</div><div class="rm">{s} · {d}</div></div><span class="chip chip-b">read</span></div>'
        return h
    def memory_rows():
        mem=get_memory()
        if not mem: return '<div class="empty">Auto-populates after cron runs.</div>'
        return "".join(f'<div class="mline">{m}</div>' for m in mem)
    def shared_html():
        secs=get_shared_sections()
        if not secs: return '<div class="empty">Agents write here 6-7am daily.</div>'
        h=""
        for s in secs:
            h+=f'<div class="sec-label">{s["h"]}</div>'
            for line in s["lines"][:5]: h+=f'<div class="mline">{line}</div>'
        return h
    if page=="agents":
        body=metrics(("Agents","9","g","all profiles active"),("Sessions",str(ts),"","across all agents"),("Skills",str(tk),"","loaded per agent"),("Cron jobs",str(len(crons)),"","active"))
        body+=agent_grid()
        body+='<div class="g2">'+co("Recent activity",f"{ts} total","chip-g")+activity_rows()+cc+'<div class="col">'+co("Cron schedule",f"{len(crons)} active","chip-g")+cron_rows()+cc+co("Memory snapshot","MEMORY.md")+memory_rows()+cc+"</div></div>"
        title,sub="Agent dashboard",f"9 agents · {ts} sessions · Hermes Codex 5.3"
    elif page=="briefing":
        briefings=get_briefings()
        body=metrics(("Briefings",str(len(briefings)),"g","saved to disk"),("Next run","7:30am","","coordinator"),("Source agents","4","","researcher · strategist · growth · sales"),("Delivery","telegram","","plus disk"))
        body+='<div class="g2">'+co("Briefing archive",f"{len(briefings)} files","chip-g")+file_rows(briefings,"briefings")+cc
        body+=co("Pipeline","coordinator")+'<div class="mline">6:00am — Researcher: market shifts</div><div class="mline">6:20am — Strategist: competitor intel</div><div class="mline">6:40am — Growth: content angles</div><div class="mline">7:00am — Sales: lead signals</div><div class="mline">7:30am — Coordinator synthesizes all four to Telegram and disk</div>'+cc+"</div>"
        title,sub="Morning briefing","daily intel · coordinator · 7:30am UTC"
    elif page=="market":
        body=metrics(("Sections today",str(len(get_shared_sections())),"g","/shared-memory/"),("Next scan","6:00am","","researcher"),("Topics","4","","market · comp · content · leads"),("API","Exa","","neural search"))
        body+=co("Today's agent research","live","chip-g")+shared_html()+cc
        body+='<div style="margin-top:.75rem">'+co("Sources")+'<div class="mline">EXA_API_KEY — neural web search via exa.ai</div><div class="mline">/shared-memory/RESEARCH.md — agent write target</div><div class="mline">~/reports/briefings/ — synthesized summaries</div>'+cc+"</div>"
        title,sub="Market research","daily scans · 6-7am UTC · Exa"
    elif page=="competitors":
        comp=get_reports("competitors")
        body=metrics(("Reports",str(len(comp)),"g","on disk"),("Next scrape","Mon 8am","","GTM Monday Intel"),("Tracking","8 competitors","","2-week rotation"),("Exa cost","~$0.02/run","","months of runway"))
        body+=co("Competitor reports",f"{len(comp)} files","chip-b")+file_rows(comp,"competitors")+cc
        body+='<div class="g2" style="margin-top:.75rem">'+co("Group A — odd weeks")+'<div class="mline">Pluriza — AI intelligence for SMBs</div><div class="mline">IRIS IQ — governance-first agents</div><div class="mline">SmallForce — AI workforce for small biz</div><div class="mline">Lindy — AI assistant SMB pricing</div>'+cc
        body+=co("Group B — even weeks")+'<div class="mline">Andron — AI workflow automation</div><div class="mline">Flow Automations — $99/$299 realtor ICP</div><div class="mline">Automiq AI — SMB automation</div><div class="mline">Arahi AI — SMB automation</div>'+cc+"</div>"
        title,sub="Competitor intel","8 SMB competitors · 2-week rotation · Monday 8am"
    elif page=="content":
        drafts=get_content_drafts()
        body=metrics(("Drafts",str(len(drafts)),"a" if drafts else "","~/content/drafts/"),("Next drop","Fri 8am","","GTM Friday"),("Formats","3","","LinkedIn · Twitter · Blog"),("Agent","Growth","","drafts to review to post"))
        body+=co("Content drafts",f"{len(drafts)} files","chip-g")+file_rows(drafts,"drafts")+cc
        body+='<div style="margin-top:.75rem">'+co("Pipeline")+'<div class="mline">Friday 8am — Growth scans trending SMB topics via Exa</div><div class="mline">Reads Monday comp report for positioning angles</div><div class="mline">Drafts 3 LinkedIn hooks + 2 Twitter openers + 1 blog idea</div><div class="mline">Saves to ~/content/drafts/YYYY-MM-DD-hooks.md</div><div class="mline">Delivers summary to Telegram for review</div>'+cc+"</div>"
        title,sub="Content angles","weekly drafts · Friday 8am · growth agent"
    elif page=="leads":
        secs=[s for s in get_shared_sections() if "lead" in s["h"].lower() or "signal" in s["h"].lower()]
        body=metrics(("Today's signals",str(sum(len(s["lines"]) for s in secs)),"g","sales agent"),("Next scan","7:00am","","daily"),("Signal types","3","","hiring · funding · ops pain"),("ICP","SMB 1-20","","services cos"))
        if secs:
            body+=co("Today's lead signals","sales · 7am","chip-g")
            for s in secs:
                for line in s["lines"][:6]: body+=f'<div class="mline">{line}</div>'
            body+=cc
        else:
            body+=co("Today's lead signals","sales · 7am")+'<div class="empty">Populates at 7:00am after sales agent runs.</div>'+cc
        body+='<div style="margin-top:.75rem">'+co("What sales agent looks for")+'<div class="mline">SMBs posting about being overwhelmed or needing to hire</div><div class="mline">1-20 employee cos with fresh seed funding</div><div class="mline">Job postings for operations manager or executive assistant</div><div class="mline">LinkedIn founders complaining about admin overhead</div>'+cc+"</div>"
        title,sub="Lead signals","daily scan · sales agent · 7am UTC"
    elif page=="midwest":
        comp=get_reports("competitors"); drafts=get_content_drafts()
        leads=get_leads("enriched"); raw=get_leads("raw"); outreach=get_outreach()
        body=metrics(
            ("Leads today",str(len(raw)),"g","~/leads/raw/"),
            ("Outreach ready",str(len(outreach)),"a" if outreach else "","~/outreach/ready/"),
            ("Comp reports",str(len(comp)),"","on disk"),
            ("Price","$129/mo","g","service businesses"),
        )
        body+='<div class="g2">'
        body+=co("Today\'s leads — click to read","enriched · 6:20am","chip-g")+file_rows(leads,"enriched")+cc
        body+=co("Outreach drafts — click to copy","growth · 6:40am","chip-b")+file_rows(outreach,"outreach/ready")+cc
        body+="</div>"
        body+='<div class="g2">'
        body+=co("Competitor reports","strategist · Monday","chip-b")+file_rows(comp[:4],"competitors")+cc
        body+=co("Content drafts","growth · Friday","chip-g")+file_rows(drafts[:4],"drafts")+cc
        body+="</div>"
        body+=co("Product & ICP")
        body+='<div class="mline">Product: ContractorOS — CRM + invoicing + vendor mgmt + reporting, web app, $129/mo flat</div>'
        body+='<div class="mline">ICP: Landscapers, HVAC, plumbers, contractors, remodelers — under 50 employees, Midwest first</div>'
        body+='<div class="mline">Signals: admin overwhelm posts, ops/admin job postings, scaling pain mentions</div>'
        body+='<div class="mline">Outreach: pain-first LinkedIn DM under 280 chars, email fallback — never mention AI first</div>'
        body+='<div class="mline">Anti-SaaS angle: replaces QuickBooks + Jobber + CRM ($180+/mo fragmented) with one platform</div>'
        body+=cc
        title,sub="Midwest Workflow Co.","ContractorOS · $129/mo · service businesses · Kenosha + Midwest"
    elif page=="dockside":
        body=metrics(("Season","pre-season","a","Kenosha · Racine"),("Agent config","pending","","not set up"),("Outreach cron","pending","","not configured"),("Booking data","pending","","not tracked"))
        body+='<div class="g2">'+co("Marina status")+'<div class="drow"><div class="rt">Kenosha marina</div><span class="chip chip-n">not tracked</span></div><div class="drow"><div class="rt">Racine marina</div><span class="chip chip-n">not tracked</span></div><div class="drow"><div class="rt">Season outreach cron</div><span class="chip chip-n">pending</span></div><div class="drow"><div class="rt">Booking pipeline</div><span class="chip chip-n">pending</span></div>'+cc
        body+=co("Setup checklist")+'<div class="mline">1. Create Dockside agent profile in Hermes</div><div class="mline">2. Configure marina season outreach cron spring</div><div class="mline">3. Connect booking data from docksideboatcare.com/admin</div><div class="mline">4. Set up marine detailing competitor pricing scan</div><div class="mline">5. Wire revenue data to this dashboard</div>'+cc+"</div>"
        title,sub="Dockside Boat Care","mobile marine detailing · Kenosha and Racine"
    elif page=="crons":
        body=metrics(("Active jobs",str(len(crons)),"g","all running"),("Daily scans","5","","6-7:30am UTC"),("Weekly intel","2","","Mon + Fri"),("Delivery","telegram","","morning briefing"))
        body+=co("All scheduled jobs",f"{len(crons)} active","chip-g")+cron_rows()+cc
        body+='<div style="margin-top:.75rem">'+co("Schedule overview")+'<div class="mline">6:00am daily  — Market scan    (researcher to /shared-memory/)</div><div class="mline">6:20am daily  — Competitive    (strategist to /shared-memory/)</div><div class="mline">6:40am daily  — Content scan   (growth to /shared-memory/)</div><div class="mline">7:00am daily  — Lead scan      (sales to /shared-memory/)</div><div class="mline">7:30am daily  — Briefing       (coordinator to Telegram + disk)</div><div class="mline">8:00am Monday — GTM deep scrape (strategist to ~/reports/)</div><div class="mline">8:00am Friday — Content batch  (growth to ~/content/drafts/)</div>'+cc+"</div>"
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
        body+=cc+co("Skill packs",f"{len(packs)} packs")
        body+="".join(f'<div class="drow"><div class="rt">{p["name"]}/</div><span class="chip chip-n">{p["count"]} skills</span></div>' for p in packs)
        body+=cc+"</div>"
        title,sub="Skills library",f"{tk} total · 9 agents · ~/.hermes/skills/"
    elif page=="world":
        world=get_world_reports()
        body=metrics(("Reports",str(len(world)),"g","~/reports/world/"),("Next scan","5:30am","","researcher agent"),("Covers","3 topics","","markets · geopolitics · SMB/AI"),("Delivery","dashboard","","no Telegram"))
        body+=co("World briefing archive — click to read",f"{len(world)} reports","chip-g")+file_rows(world,"world")+cc
        body+='<div style="margin-top:.75rem">'+co("What researcher scans")+'<div class="mline">Markets: S&P 500 moves, crypto top movers, Fed signals, macro shifts</div><div class="mline">Geopolitics: 2-3 developments that could affect US business or markets</div><div class="mline">SMB + AI: funding news, layoffs, new tools, regulatory moves</div><div class="mline">So What: 1-2 lines on what it means for Midwest Workflow or your investments</div>'+cc+"</div>"
        title,sub="World briefing","daily scan · 5:30am UTC · researcher agent"
    else:
        body='<div class="empty">Page not found.</div>'; title,sub="404",""
    html=SHELL.replace("{{TITLE}}",title).replace("{{SUB}}",sub).replace("{{NOW}}",now).replace("{{BODY}}",body)
    for p in ["briefing","market","competitors","content","leads","world","agents","crons","skills","midwest","dockside"]:
        html=html.replace("{{"+p+"}}","active" if p==page else "")
    return html

@app.get("/",response_class=HTMLResponse)
async def root(session:str=Cookie(default=None)):
    return RedirectResponse("/page/agents")
@app.get("/page/{page}",response_class=HTMLResponse)
async def page_view(page:str,session:str=Cookie(default=None)):
    if not is_authed(session): return RedirectResponse("/login")
    return HTMLResponse(_build_page(page,datetime.utcnow().strftime("%a %b %d %Y · %H:%M UTC")))

LOGIN_HTML='<!DOCTYPE html><html><head><meta charset="utf-8"><title>Business OS</title><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet"><style>*{box-sizing:border-box;margin:0;padding:0}body{background:#0a0c10;color:#c8d0d8;font-family:\'IBM Plex Sans\',sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}.box{width:360px;border:1px solid #1e2530;border-radius:8px;padding:2.5rem;background:#0e1117}h1{font-family:\'IBM Plex Mono\',monospace;font-size:15px;color:#e8edf2;margin-bottom:.25rem}p{font-size:12px;color:#5a6476;margin-bottom:2rem}label{font-size:10px;color:#5a6476;text-transform:uppercase;letter-spacing:.08em;display:block;margin-bottom:.4rem}input{width:100%;background:#0a0c10;border:1px solid #1e2530;color:#c8d0d8;padding:.65rem .85rem;border-radius:5px;font-family:\'IBM Plex Mono\',monospace;font-size:14px;outline:none;margin-bottom:1.25rem}input:focus{border-color:#3d8b6e}button{width:100%;background:#1a3d2e;border:1px solid #2a6b4e;color:#4eca8e;padding:.7rem;border-radius:5px;font-family:\'IBM Plex Mono\',monospace;font-size:13px;cursor:pointer}.err{color:#e05555;font-size:12px;margin-bottom:.75rem}</style></head><body><div class="box"><h1>BUSINESS OS</h1><p>Sean Fitzgerald · Kenosha, WI</p><form method="post" action="/login"><label>Access code</label><input type="password" name="password" autofocus><button>ENTER</button></form></div></body></html>'

SHELL="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{TITLE}} - Business OS</title><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet"><style>*{box-sizing:border-box;margin:0;padding:0}:root{--bg0:#0a0c10;--bg1:#0e1117;--bg2:#131820;--bo:#1e2530;--bo2:#2a3548;--t0:#e8edf2;--t1:#9aa5b4;--t2:#5a6476;--t3:#3a4456;--green:#4eca8e;--gd:#1a3d2e;--gb:#2a6b4e;--amber:#f0a832;--ad:#3a2a10;--ab:#6b4a1e;--blue:#5b9cf6;--bd:#162040;--bb:#2a4a8e;--mono:\'IBM Plex Mono\',monospace;--sans:\'IBM Plex Sans\',sans-serif}body{background:var(--bg0);color:var(--t1);font-family:var(--sans);font-size:13px;height:100vh;display:flex;flex-direction:column;overflow:hidden}.shell{display:flex;flex:1;overflow:hidden}.sidebar{width:210px;flex-shrink:0;background:var(--bg1);border-right:1px solid var(--bo);display:flex;flex-direction:column;overflow-y:auto}.sb-brand{padding:.85rem 1rem;border-bottom:1px solid var(--bo)}.sb-logo{font-family:var(--mono);font-size:12px;font-weight:500;color:var(--t0);display:flex;align-items:center;gap:6px}.sb-dot{width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 5px var(--green)}.sb-time{font-family:var(--mono);font-size:10px;color:var(--t3);margin-top:3px}.sb-sec{padding:.6rem 1rem .2rem;font-family:var(--mono);font-size:9px;color:var(--t3);text-transform:uppercase;letter-spacing:.1em}.sb-item{display:flex;align-items:center;gap:8px;padding:.42rem .7rem;margin:1px 5px;border-radius:5px;color:var(--t2);font-size:11px;text-decoration:none;transition:background .1s,color .1s}.sb-item:hover{background:var(--bg2);color:var(--t1)}.sb-item.active{background:rgba(78,202,142,.1);color:var(--green)}.sb-item.active .sb-ic{color:var(--green)}.sb-ic{font-size:11px;width:14px;text-align:center;color:var(--t3);flex-shrink:0}.sb-badge{margin-left:auto;font-family:var(--mono);font-size:9px;padding:1px 5px;border-radius:8px;background:rgba(78,202,142,.12);color:var(--green)}.sb-space{flex:1}.sb-foot{padding:.6rem 1rem;border-top:1px solid var(--bo);font-family:var(--mono);font-size:9px;color:var(--t3)}.main{flex:1;display:flex;flex-direction:column;overflow:hidden}.topbar{display:flex;align-items:center;justify-content:space-between;padding:.6rem 1.25rem;border-bottom:1px solid var(--bo);background:var(--bg1);flex-shrink:0}.page-title{font-family:var(--mono);font-size:13px;font-weight:500;color:var(--t0)}.page-sub{font-size:10px;color:var(--t2);margin-top:2px}.logout{font-family:var(--mono);font-size:10px;color:var(--t2);border:1px solid var(--bo);padding:3px 9px;border-radius:4px;text-decoration:none}.logout:hover{color:var(--t1)}.body{flex:1;overflow-y:auto;padding:1rem 1.25rem}.metrics{display:grid;gap:8px;margin-bottom:.9rem}.met{background:var(--bg2);border-radius:6px;padding:.7rem .85rem}.mlabel{font-family:var(--mono);font-size:9px;color:var(--t2);text-transform:uppercase;letter-spacing:.08em;margin-bottom:.25rem}.mvalue{font-size:20px;font-weight:500;color:var(--t0);font-family:var(--mono)}.mvalue.g{color:var(--green)}.mvalue.a{color:var(--amber)}.msub{font-size:10px;color:var(--t2);margin-top:.1rem}.card{background:var(--bg1);border:1px solid var(--bo);border-radius:8px;padding:.85rem 1rem;margin-bottom:.75rem}.ch{display:flex;justify-content:space-between;align-items:center;padding-bottom:.55rem;margin-bottom:.55rem;border-bottom:1px solid var(--bo)}.ct{font-family:var(--mono);font-size:9px;color:var(--t2);text-transform:uppercase;letter-spacing:.08em}.g2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:.75rem;margin-bottom:.75rem}.col{display:flex;flex-direction:column;gap:.75rem}.agent-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-bottom:.75rem}.agent-card{background:var(--bg2);border:1px solid var(--bo);border-radius:6px;padding:.6rem .75rem;cursor:pointer;transition:border-color .12s}.agent-card:hover{border-color:var(--gb)}.ac-row{display:flex;justify-content:space-between;align-items:center}.aname{font-size:12px;font-weight:500;color:var(--t0);display:flex;align-items:center;gap:5px}.adesc{font-size:10px;color:var(--t2);margin-top:2px}.sc{font-size:9px;color:var(--t2);font-family:var(--mono);margin-top:2px}.drow{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--bo)}.drow:last-child{border-bottom:none}.drow.clickable{cursor:pointer}.drow.clickable:hover .rt{color:var(--green)}.rt{font-size:11px;font-weight:500;color:var(--t0)}.rm{font-size:10px;color:var(--t2);font-family:var(--mono);margin-top:1px}.mline{font-size:11px;color:var(--t1);padding:4px 0;border-bottom:1px solid var(--bo);font-family:var(--mono);line-height:1.5}.mline:last-child{border-bottom:none}.sec-label{font-family:var(--mono);font-size:9px;color:var(--t2);text-transform:uppercase;letter-spacing:.08em;margin:.4rem 0 .2rem}.empty{font-size:11px;color:var(--t2);font-style:italic;padding:.35rem 0;font-family:var(--mono)}.dot{width:5px;height:5px;border-radius:50%;display:inline-block;flex-shrink:0}.dot-g{background:var(--green);box-shadow:0 0 3px var(--green)}.dot-a{background:var(--amber)}.chip{font-family:var(--mono);font-size:9px;padding:2px 6px;border-radius:8px;border:1px solid transparent;white-space:nowrap}.chip-g{background:var(--gd);color:var(--green);border-color:var(--gb)}.chip-a{background:var(--ad);color:var(--amber);border-color:var(--ab)}.chip-n{background:var(--bg2);color:var(--t2);border-color:var(--bo)}.chip-b{background:var(--bd);color:var(--blue);border-color:var(--bb)}.mono-chip{font-family:var(--mono);font-size:9px;padding:2px 6px;border-radius:4px;background:var(--bg0);border:1px solid var(--bo2);color:var(--t2)}.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:200;align-items:flex-start;justify-content:center;padding:2rem;overflow-y:auto}.overlay.open{display:flex}.modal{background:var(--bg1);border:1px solid var(--bo2);border-radius:10px;width:100%;max-width:800px;margin:auto}.mhead{display:flex;justify-content:space-between;align-items:center;padding:.85rem 1.1rem;border-bottom:1px solid var(--bo)}.mtitle{font-family:var(--mono);font-size:13px;font-weight:500;color:var(--t0)}.mclose{background:none;border:1px solid var(--bo);color:var(--t2);font-family:var(--mono);font-size:11px;padding:3px 9px;border-radius:4px;cursor:pointer}.mclose:hover{color:var(--t0)}.mbody{padding:1.1rem;max-height:78vh;overflow-y:auto}.msec{margin-bottom:1rem}.msec-title{font-family:var(--mono);font-size:9px;color:var(--t2);text-transform:uppercase;letter-spacing:.08em;margin-bottom:.35rem;padding-bottom:.3rem;border-bottom:1px solid var(--bo)}.sblock{font-family:var(--mono);font-size:10px;color:var(--t1);white-space:pre-wrap;background:var(--bg0);border:1px solid var(--bo);border-radius:4px;padding:.65rem .8rem;line-height:1.8;max-height:280px;overflow-y:auto}.sess-row{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--bo);cursor:pointer}.sess-row:last-child{border-bottom:none}.sess-row:hover .sess-name{color:var(--green)}.sess-name{font-size:11px;font-family:var(--mono);color:var(--t0)}.sess-meta{font-size:10px;color:var(--t2)}.sess-exp{background:var(--bg0);border:1px solid var(--bo);border-radius:4px;padding:.6rem;margin:4px 0;display:none}.sess-exp.open{display:block}.pack-row{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--bo)}.pack-row:last-child{border-bottom:none}.pack-name{font-size:11px;font-family:var(--mono);color:var(--t0)}.pack-desc{font-size:10px;color:var(--t2)}.pack-cnt{font-size:9px;font-family:var(--mono);color:var(--green)}.pills{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px}.pill{font-size:9px;font-family:var(--mono);padding:2px 6px;border-radius:4px;background:var(--bg2);border:1px solid var(--bo2);color:var(--t2)}.loading{font-family:var(--mono);font-size:11px;color:var(--t2);padding:.75rem 0}.col-sec{border-bottom:1px solid var(--bo)}.col-hd{display:flex;align-items:center;gap:.4rem;padding:.5rem 0;cursor:pointer;user-select:none}.col-arrow{font-size:9px;color:var(--t2);width:10px;flex-shrink:0}.col-arrow.open{color:var(--green)}.col-tag{margin-left:auto;font-family:var(--mono);font-size:9px;color:var(--t2);padding:1px 6px;border-radius:8px;background:var(--bg2);border:1px solid var(--bo)}.col-body{display:none;padding-bottom:.5rem}.col-body.open{display:block}.col-sec{border-bottom:1px solid var(--bo)}.col-hd{display:flex;align-items:center;gap:.4rem;padding:.5rem 0;cursor:pointer;user-select:none}.col-arrow{font-size:9px;color:var(--t2);width:10px;flex-shrink:0}.col-arrow.open{color:var(--green)}.col-tag{margin-left:auto;font-family:var(--mono);font-size:9px;color:var(--t2);padding:1px 6px;border-radius:8px;background:var(--bg2);border:1px solid var(--bo)}.col-body{display:none;padding-bottom:.5rem}.col-body.open{display:block}</style></head><body><div class="shell"><nav class="sidebar"><div class="sb-brand"><div class="sb-logo"><span class="sb-dot"></span>BUSINESS OS</div><div class="sb-time">{{NOW}}</div></div><div class="sb-sec">Intelligence</div><a href="/page/briefing" class="sb-item {{briefing}}"><span class="sb-ic">o</span>Morning briefing<span class="sb-badge">7:30am</span></a><a href="/page/market" class="sb-item {{market}}"><span class="sb-ic">o</span>Market research</a><a href="/page/competitors" class="sb-item {{competitors}}"><span class="sb-ic">o</span>Competitor intel</a><a href="/page/content" class="sb-item {{content}}"><span class="sb-ic">o</span>Content angles</a><a href="/page/world" class="sb-item {{world}}"><span class="sb-ic">o</span>World briefing</a><a href="/page/leads" class="sb-item {{leads}}"><span class="sb-ic">o</span>Lead signals</a><div class="sb-sec">Operations</div><a href="/page/agents" class="sb-item {{agents}}"><span class="sb-ic">o</span>Agent dashboard</a><a href="/page/crons" class="sb-item {{crons}}"><span class="sb-ic">o</span>Cron schedule</a><a href="/page/skills" class="sb-item {{skills}}"><span class="sb-ic">o</span>Skills library</a><div class="sb-sec">Ventures</div><a href="/page/midwest" class="sb-item {{midwest}}"><span class="sb-ic">o</span>Midwest Workflow</a><a href="/page/dockside" class="sb-item {{dockside}}"><span class="sb-ic">o</span>Dockside Boat Care</a><div class="sb-space"></div><div class="sb-foot">Hetzner FSN1 - port 8000</div></nav><div class="main"><div class="topbar"><div><div class="page-title">{{TITLE}}</div><div class="page-sub">{{SUB}}</div></div><a href="/logout" class="logout">logout</a></div><div class="body">{{BODY}}</div></div></div><div class="overlay" id="agentOv" onclick="closeBg(event,\'agentOv\')"><div class="modal"><div class="mhead"><span class="mtitle" id="agentTitle">Agent</span><button class="mclose" onclick="closeModal(\'agentOv\')">CLOSE X</button></div><div class="mbody" id="agentBody"><div class="loading">Loading...</div></div></div></div><div class="overlay" id="sessOv" onclick="closeBg(event,\'sessOv\')"><div class="modal" style="max-width:680px"><div class="mhead"><span class="mtitle" id="sessTitle">Session</span><button class="mclose" onclick="closeModal(\'sessOv\')">CLOSE X</button></div><div class="mbody" id="sessBody"><div class="loading">Loading...</div></div></div></div><script>const AL={coordinator:"Coordinator",designer:"Designer",developer:"Developer",devops:"DevOps",growth:"Growth",product:"Product",researcher:"Researcher",sales:"Sales",strategist:"Strategist"};function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}async function openAgent(name){
  document.getElementById("agentTitle").textContent=AL[name]||name;
  document.getElementById("agentBody").innerHTML='<div class="loading">Loading...</div>';
  document.getElementById("agentOv").classList.add("open");
  try{
    const d=await fetch("/api/agent/"+name).then(r=>r.json());
    var h="";
    h+='<div class="col-sec"><div class="col-hd" onclick="toggleCol('soul-'+name+'')">'
     +'<span class="col-arrow" id="arr-soul-'+name+'">+</span>'
     +'<span class="msec-title" style="display:inline;margin-left:6px">SOUL.md</span>'
     +'<span class="col-tag">persona</span></div>'
     +'<div class="col-body" id="soul-'+name+'"><div class="md-body">'+renderMd(d.soul||"(empty)")+'</div></div></div>';
    h+='<div class="col-sec"><div class="col-hd" onclick="toggleCol('skills-'+name+'')">'
     +'<span class="col-arrow" id="arr-skills-'+name+'">+</span>'
     +'<span class="msec-title" style="display:inline;margin-left:6px">Skills</span>'
     +'<span class="col-tag">'+d.skill_count+' loaded</span></div>'
     +'<div class="col-body" id="skills-'+name+'">';
    if(!d.packs||!d.packs.length){h+='<div class="empty">No packs.</div>';}
    else{(d.packs||[]).forEach(function(p){
      h+='<div class="pack-row"><div><div class="pack-name">'+p.name+'/</div>'
       +(p.desc?'<div class="pack-desc">'+esc(p.desc)+'</div>':'')
       +'</div><span class="pack-cnt">'+p.count+'</span></div>';
    });}
    h+='</div></div>';
    h+='<div class="col-sec"><div class="col-hd" onclick="toggleCol('sess-'+name+'')">'
     +'<span class="col-arrow open" id="arr-sess-'+name+'">v</span>'
     +'<span class="msec-title" style="display:inline;margin-left:6px">Sessions</span>'
     +'<span class="col-tag">'+(d.sessions||[]).length+' runs</span></div>'
     +'<div class="col-body open" id="sess-'+name+'">';
    if(!d.sessions||!d.sessions.length){h+='<div class="empty">No sessions.</div>';}
    else{d.sessions.forEach(function(s,i){
      var sc=s.platform==="telegram"?"chip-b":"chip-n";
      h+='<div class="sess-row" onclick="toggleSess('se'+i+'',''+name+'',''+s.session_id+'')">'
       +'<div><div class="sess-name">'+s.fmt_start+'</div>'
       +'<div class="sess-meta">'+s.duration+' - '+(s.platform||"cron")+'</div></div>'
       +'<span class="chip '+sc+'">'+(s.platform||"cron")+'</span></div>'
       +'<div class="sess-exp" id="se'+i+'"><div class="loading">Loading...</div></div>';
    });}
    h+='</div></div>';
    document.getElementById("agentBody").innerHTML=h;
  }catch(e){document.getElementById("agentBody").innerHTML='<div class="empty">Error: '+e.message+'</div>';}}
async function toggleSess(id,agent,sid){const el=document.getElementById(id);if(el.classList.contains("open")){el.classList.remove("open");return;}el.classList.add("open");if(el.dataset.loaded)return;el.dataset.loaded="1";try{const d=await fetch("/api/session/"+agent+"/"+sid).then(r=>r.json());let h="";if(d.first_user)h+="<div class=\\"msec-title\\">Task</div><div class=\\"sblock\\" style=\\"max-height:130px\\">"+esc(d.first_user)+"</div>";if(d.last_assistant)h+="<div class=\\"msec-title\\" style=\\"margin-top:.5rem\\">Result</div><div class=\\"sblock\\" style=\\"max-height:150px\\">"+esc(d.last_assistant)+"</div>";el.innerHTML=h||"<div class=\\"empty\\">Could not parse session.</div>";}catch(e){el.innerHTML="<div class=\\"empty\\">Error.</div>";}}async function openSession(agent,sid){document.getElementById("sessTitle").textContent=(AL[agent]||agent)+" - "+sid.slice(0,8);document.getElementById("sessBody").innerHTML="<div class=\\"loading\\">Loading...</div>";document.getElementById("sessOv").classList.add("open");try{const d=await fetch("/api/session/"+agent+"/"+sid).then(r=>r.json());let h="";if(d.first_user)h+="<div class=\\"msec\\"><div class=\\"msec-title\\">Task</div><div class=\\"sblock\\">"+esc(d.first_user)+"</div></div>";if(d.last_assistant)h+="<div class=\\"msec\\"><div class=\\"msec-title\\">Result</div><div class=\\"sblock\\">"+esc(d.last_assistant)+"</div></div>";document.getElementById("sessBody").innerHTML=h||"<div class=\\"empty\\">Could not parse.</div>";}catch(e){document.getElementById("sessBody").innerHTML="<div class=\\"empty\\">Error: "+e.message+"</div>";}}async function openFile(folder,filename){document.getElementById("sessTitle").textContent=filename;document.getElementById("sessBody").innerHTML="<div class=\\"loading\\">Loading...</div>";document.getElementById("sessOv").classList.add("open");try{const d=await fetch("/api/file/"+folder+"/"+encodeURIComponent(filename)).then(r=>r.json());if(d.error){document.getElementById("sessBody").innerHTML="<div class=\\"empty\\">"+esc(d.error)+"</div>";return;}document.getElementById("sessBody").innerHTML="<div class=\\"msec\\"><div class=\\"sblock\\" style=\\"max-height:65vh\\">"+esc(d.content)+"</div></div>";}catch(e){document.getElementById("sessBody").innerHTML="<div class=\\"empty\\">Error: "+e.message+"</div>";}}function toggleCol(id){var b=document.getElementById(id);var a=document.getElementById("arr-"+id);if(!b)return;b.classList.toggle("open");if(a){a.innerHTML=b.classList.contains("open")?"v":">";a.classList.toggle("open",b.classList.contains("open"));}}function toggleCol(id){var b=document.getElementById(id);var a=document.getElementById("arr-"+id);if(!b)return;b.classList.toggle("open");if(a){a.innerHTML=b.classList.contains("open")?"v":">";a.classList.toggle("open",b.classList.contains("open"));}}function closeModal(id){document.getElementById(id).classList.remove("open");}function closeBg(e,id){if(e.target===document.getElementById(id))closeModal(id);}document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeModal("agentOv");closeModal("sessOv");}});setTimeout(()=>location.reload(),60000);</script></body></html>"""

if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=8000,log_level="warning")
