
import json, re, io
from datetime import datetime, timedelta
from pathlib import Path
import streamlit as st
import pandas as pd

APP_TITLE = "Cynosure 2025 — Secure Event Portal"

# ---------- Utils ----------
def norm(s: str) -> str:
    if not s: return ""
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def ekey(name: str) -> str: return norm(name)
def nkey(name: str) -> str: return norm(name)

# ---------- Data ----------
DATA_PATH = Path(__file__).with_name("cynosure_events.json")
if not DATA_PATH.exists():
    st.error("Missing cynosure_events.json next to the app file."); st.stop()
EVENTS = json.loads(DATA_PATH.read_text(encoding="utf-8")).get("events", [])
EVENTS_BY_KEY = {ekey(ev["name"]): ev for ev in EVENTS}

STORE_PATH = Path(__file__).with_name("participants_store.json")
DEFAULT_STORE = {"participants": [], "messages": [], "completions": [], "sessions": [], "updated_at": ""}

def load_store():
    if not STORE_PATH.exists():
        STORE_PATH.write_text(json.dumps(DEFAULT_STORE, ensure_ascii=False), encoding="utf-8")
    try:
        store = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        store = dict(DEFAULT_STORE)
    changed = False
    for p in store.get("participants", []):
        if "name_key" not in p: p["name_key"] = nkey(p.get("name","")); changed = True
        if "event_key" not in p: p["event_key"] = ekey(p.get("event","")); changed = True
        p.setdefault("phone",""); p.setdefault("email",""); p.setdefault("grade",""); p.setdefault("subcat","")
    for m in store.get("messages", []):
        m.setdefault("to_key", nkey(m.get("to",""))); m.setdefault("from_key", nkey(m.get("from",""))); m.setdefault("event_key", ekey(m.get("event","")))
    if changed: save_store(store)
    return store

def save_store(store):
    store["updated_at"] = datetime.now().isoformat()
    STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")

def upsert_session(name: str, role: str):
    s = load_store()
    now = datetime.now().isoformat()
    nk = nkey(name)
    for row in s.get("sessions", []):
        if row.get("name_key")==nk:
            row["name"] = name; row["role"] = role; row["last_seen"] = now
            save_store(s); return
    s.setdefault("sessions", []).append({"name": name, "name_key": nk, "role": role, "last_seen": now})
    save_store(s)

# Optional seed
def maybe_seed():
    s = load_store()
    if not s["participants"] and EVENTS:
        demo = {"event": EVENTS[0]["name"], "event_key": ekey(EVENTS[0]["name"]), "name": "Demo User", "name_key": nkey("Demo User"),
                "phone":"", "email":"", "grade":"", "subcat":""}
        s["participants"].append(demo); save_store(s)
maybe_seed()

# ---------- Time helpers ----------
def parse_datetime_fields(ev: dict):
    text_date = ev.get("date") or ev.get("date_info_duty","")
    text_time = ev.get("time","")
    up_date = (text_date or "").upper()

    start_day = end_day = None
    if "FRIDAY" in up_date or "26" in up_date: start_day = "2025-09-26"
    if "SATURDAY" in up_date or "27" in up_date:
        if start_day: end_day = "2025-09-27"
        else: start_day = "2025-09-27"
    if "BOTH" in up_date:
        start_day, end_day = "2025-09-26", "2025-09-27"

    tpat = re.compile(r'(\d{1,2}:\d{2}\s*(?:A\.M\.|P\.M\.|AM|PM|Noon|NOON)|\d{1,2}\s*(?:A\.M\.|P\.M\.|AM|PM))')
    matches = [m.group(1) for m in tpat.finditer(text_time or "")]
    def tparse(s):
        s = s.replace("A.M.","AM").replace("P.M.","PM").replace("NOON","12:00 PM").replace("Noon","12:00 PM")
        s = re.sub(r'(?<=\d)\s*(AM|PM)$', r' \1', s)
        for fmt in ("%I:%M %p", "%I %p"):
            try:
                return datetime.strptime(s.strip(), fmt).time()
            except:
                pass
        return None
    stime = tparse(matches[0]) if len(matches)>=1 else None
    etime = tparse(matches[1]) if len(matches)>=2 else None

    sdt = edt = None
    if start_day and stime:
        sdt = datetime.strptime(start_day, "%Y-%m-%d").replace(hour=stime.hour, minute=stime.minute)
    elif start_day:
        sdt = datetime.strptime(start_day, "%Y-%m-%d").replace(hour=9, minute=0)

    if end_day and etime:
        edt = datetime.strptime(end_day, "%Y-%m-%d").replace(hour=etime.hour, minute=etime.minute)
    elif sdt and etime:
        edt = sdt.replace(hour=etime.hour, minute=etime.minute)
    elif sdt and not etime:
        edt = sdt + timedelta(hours=2)

    return sdt, edt

def badge(sdt, edt):
    now = datetime.now()
    if not sdt: 
        return "⏱️ Time TBD"
    if now < sdt:
        delta = sdt - now
        days = delta.days
        hours = int(delta.seconds // 3600)
        mins = int((delta.seconds % 3600) // 60)
        if days > 0:
            return f"🕒 Starts in {days}d {hours}h {mins}m"
        return f"🕒 Starts in {hours}h {mins}m"
    if edt and now > edt:
        return "✅ Completed"
    return "🔴 On-going"

# ---------- Messaging & store helpers ----------
def send_message(to_name, from_name, ev_name, text, to_role):
    if not text.strip(): return
    s = load_store()
    s["messages"].append({
        "to": to_name, "to_key": nkey(to_name),
        "from": from_name, "from_key": nkey(from_name),
        "event": ev_name, "event_key": ekey(ev_name),
        "to_role": to_role,
        "text": text.strip(),
        "timestamp": datetime.now().isoformat()
    })
    save_store(s)

def event_participants(ev_name, subcat=None):
    s = load_store()
    evk = ekey(ev_name)
    rows = [p for p in s["participants"] if p.get("event_key")==evk]
    if subcat and subcat!="All":
        rows = [p for p in rows if (p.get("subcat") or "")==subcat]
    rows.sort(key=lambda p: (p.get("subcat") or "", p.get("name","").lower()))
    return rows

def upsert_participant(ev_name, name, phone, email, grade, subcat):
    s = load_store()
    evk, nk = ekey(ev_name), nkey(name)
    sc = subcat or ""
    for p in s["participants"]:
        if p["event_key"]==evk and p["name_key"]==nk and (p.get("subcat") or "")==sc:
            p.update({"name":name.strip(),"phone":phone.strip(),"email":email.strip(),"grade":grade.strip(),"subcat":sc})
            save_store(s); return
    s["participants"].append({"event": ev_name, "event_key": evk, "name": name.strip(), "name_key": nk,
                              "phone": phone.strip(), "email": email.strip(), "grade": grade.strip(), "subcat": sc})
    save_store(s)

def remove_participant(ev_name, name, subcat_display):
    s = load_store()
    evk, nk = ekey(ev_name), nkey(name)
    sc = subcat_display or ""
    s["participants"] = [p for p in s["participants"] if not (p["event_key"]==evk and p["name_key"]==nk and (p.get("subcat") or "")==sc)]
    save_store(s)


def derive_categories(ev: dict):
    '''
    Return a list of ONLY brochure-derived categories:
    - Age categories (split I., II., III. or single span)
    - Gender categories (Girls/Boys) when specified
    '''
    blk = (ev.get("brochure_block") or "") + " " + (ev.get("time") or "") + " " + (ev.get("date") or ev.get("date_info_duty",""))
    text = re.sub(r"\s+", " ", blk, flags=re.S).strip()

    cats = []

    # ---- Gender detection ----
    gender_hits = 0
    if re.search(r"\bgirls?\s+team", text, flags=re.I):
        gender_hits += 1
    if re.search(r"\bboys?\s+team", text, flags=re.I):
        gender_hits += 1
    # Some sports specify "one girls team and one boys team"
    if gender_hits >= 1 and re.search(r"\bgirls?\b", text, flags=re.I) and re.search(r"\bboys?\b", text, flags=re.I):
        cats.extend(["Girls", "Boys"])

    # ---- Age Category extraction ----
    # Patterns like: "Age Category: I. 6th to 8th II. 9th to 12th"
    m = re.search(r"Age\s*Category\s*:\s*(.+?)(?:Duration|Event\s*Category|Venue|Dress|Participants|Time|$)", text, flags=re.I)
    span_text = m.group(1).strip() if m else ""

    # Split out "I. 6th to 8th"  "II. 9th to 12th"  "III: 11th to 12th"
    parts = re.findall(r"\b([IVX]+)\s*[.:]\s*([0-9]{1,2}(?:th|st|nd|rd)\s*to\s*[0-9]{1,2}(?:th|st|nd|rd))", span_text, flags=re.I)
    if parts:
        for roman, span in parts:
            pretty = f"Category {roman.upper()} : {span}"
            if pretty not in cats:
                cats.append(pretty)
    else:
        # Single span like "9th to 12th" or "8th to 12th"
        single = re.search(r"\b([0-9]{1,2}(?:th|st|nd|rd)\s*to\s*[0-9]{1,2}(?:th|st|nd|rd))\b", span_text, flags=re.I)
        if single:
            pretty = f"Category : {single.group(1)}"
            cats.append(pretty)
        else:
            # Scan whole text for a single span when none extracted
            single2 = re.search(r"\b([0-9]{1,2}(?:th|st|nd|rd)\s*to\s*[0-9]{1,2}(?:th|st|nd|rd))\b", text, flags=re.I)
            if single2:
                cats.append(f"Category : {single2.group(1)}")

    # Ensure uniqueness and stable order
    seen = set()
    out = []
    for c in cats:
        if c and c not in seen:
            out.append(c); seen.add(c)
    return out

def get_thread(ev_key, participant_nkey):
    msgs = load_store()["messages"]
    th = [m for m in msgs if m.get("event_key")==ev_key and (m.get("to_key")==participant_nkey or m.get("from_key")==participant_nkey)]
    th.sort(key=lambda x: x["timestamp"])
    return th

# ---------- Category extraction from brochure ----------
def extract_age_categories(text: str):
    if not text: return []
    cats = []
    m = re.search(r'Age\s*Category\s*:\s*(.+)', text, flags=re.IGNORECASE)
    if m:
        seg = m.group(1)
        for part in re.split(r'(?=(?:I{1,3}|IV|V)\s*[.:])', seg):
            part = part.strip(" .:\n\t")
            if not part: continue
            m2 = re.match(r'((?:I{1,3}|IV|V))\s*[.:]\s*(.+)', part)
            if m2:
                rn, rng = m2.group(1), m2.group(2).strip()
                cats.append(f"Category {rn} : {rng}")
    for line in text.splitlines():
        m3 = re.match(r'\s*Category\s*((?:I{1,3}|IV|V))\s*[:\-]\s*(.+)', line, flags=re.IGNORECASE)
        if m3:
            rn = m3.group(1).upper()
            rng = m3.group(2).strip()
            val = f"Category {rn} : {rng}"
            if val not in cats:
                cats.append(val)
    out = []
    for c in cats:
        if c not in out: out.append(c)
    return out

def extract_gender_categories(text: str):
    if not text: return []
    t = text.lower()
    if ("girls team" in t and "boys team" in t) or ("one girls team" in t and "one boys team" in t):
        return ["Girls", "Boys"]
    if re.search(r'\bgirls?\s+team\b', t) and re.search(r'\bboys?\s+team\b', t):
        return ["Girls", "Boys"]
    return []

# ---------- UI ----------
st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)
st.info(f"🕒 Now: {datetime.now().strftime('%a %d %b %Y, %I:%M %p')}")
st.caption("Participants must already be added by Admin. Case-insensitive login. Admins need password + name.")

# Login gate
mode = st.radio("Login as", ["Participant", "Admin"], horizontal=True, key="login_mode")
authorized = False
is_admin = False
current_user = None
admin_name = None

if mode == "Admin":
    pwd = st.text_input("Admin password", type="password", key="admin_pwd")
    if pwd == "vxxxk":
        admin_name = st.text_input("Admin full name", key="admin_name").strip()
        if admin_name:
            is_admin = True; authorized = True
            upsert_session(admin_name, "admin")
            st.success(f"Hello {admin_name}! Admin mode enabled.")
    elif pwd:
        st.error("Incorrect password.")
else:
    cand = st.text_input("Participant full name (must already be saved)", key="participant_name").strip()
    if cand:
        nk = nkey(cand)
        exists = any(p for p in load_store()["participants"] if p.get("name_key")==nk)
        if exists:
            authorized = True; current_user = cand
            upsert_session(cand, "participant")
            s = load_store()
            my_ev_keys = [p["event_key"] for p in s["participants"] if p["name_key"]==nk]
            soon = None
            for ek in my_ev_keys:
                ev = EVENTS_BY_KEY.get(ek); 
                if not ev: continue
                sd, ed = parse_datetime_fields(ev)
                if sd and (soon is None or sd < soon[0]): soon = (sd, ed, ev)
            if soon:
                sd, ed, ev = soon
                now = datetime.now()
                if ed and now > ed:
                    st.success(f"Hello {cand}, your event **{ev['name']}** is completed.")
                elif sd and now < sd:
                    d = sd - now
                    st.success(f"Hello {cand}, your event **{ev['name']}** starts in {d.days}d {int(d.seconds//3600)}h {int((d.seconds%3600)//60)}m.")
                else:
                    st.success(f"Hello {cand}, your event **{ev['name']}** is on-going.")
        else:
            st.error("Name not found. Ask Admin to add you to an event first.")

if not authorized:
    st.stop()

# Card renderer
def render_event_card(ev: dict, scope: str, is_admin=False, participant_name: str=None, admin_name: str=None):
    K = lambda suffix: f"{scope}_{ekey(ev['name'])}_{suffix}"

    sdt, edt = parse_datetime_fields(ev)
    st.markdown(f"### {ev['name']}")
    c1, c2, c3 = st.columns([1,1,1])
    with c1:
        st.write(f"**Category:** {ev.get('category','')}")
        st.write(f"**Age:** {ev.get('age_category','')}")
    with c2:
        if ev.get("date") or ev.get("date_info_duty"):
            st.write(f"**Date:** {ev.get('date') or ev.get('date_info_duty','')}")
        if ev.get("time"):
            st.write(f"**Time:** {ev.get('time')}")
        if ev.get("venue"):
            st.write(f"**Venue:** {ev.get('venue')}")
    with c3:
        st.write(f"**Teacher:** {ev.get('teacher_in_charge','')}")
        st.write(badge(sdt, edt))

    with st.expander("Brochure (word-for-word)"):
        block = ev.get("brochure_block","(Not found in brochure)")
        st.code(block)
        def _ics():
            def fmt(dt): return dt.strftime("%Y%m%dT%H%M%S")
            uid = f"{ekey(ev['name'])}@cynosure"
            body = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Cynosure//EN\nBEGIN:VEVENT\nUID:"+uid+"\nSUMMARY:"+ev['name']+"\n"
            if sdt: body += "DTSTART:"+fmt(sdt)+"\n"
            if edt: body += "DTEND:"+fmt(edt)+"\n"
            if ev.get("venue"): body += "LOCATION:"+ev['venue']+"\n"
            body += "DESCRIPTION:"+block.replace("\\n", " \\n ")[:1800]+"\nEND:VEVENT\nEND:VCALENDAR"
            return body.encode("utf-8")
        st.download_button("➕ Add to Calendar (.ics)", _ics(), file_name=f"{ev['name']}.ics", mime="text/calendar", key=K("ics"))

    st.divider()

    # Compute categories strictly from brochure
    block = ev.get("brochure_block","")
    age_cats = extract_age_categories(block)
    gender_cats = extract_gender_categories(block)
    if gender_cats:
        subcats = gender_cats
    elif age_cats:
        subcats = age_cats
    else:
        subcats = []

    st.subheader("Participants")
    if not subcats:
        st.info("This event has no age/gender categories in the brochure. Admins may still add participants without a category.")

    colf, colm = st.columns([1,1])
    with colf:
        sub_filter = st.selectbox("Filter by category", (["All"] + subcats) if subcats else ["All"], key=K("flt_cat"))
    with colm:
        if subcats:
            st.caption("Categories are auto-loaded from the brochure (Age or Gender only).")

    plist = event_participants(ev["name"], sub_filter if subcats else None)

    if is_admin:
        st.markdown("**Add/Update a participant**")
        current_cat = sub_filter if (sub_filter and sub_filter!="All") else (subcats[0] if subcats else "")
        if not subcats:
            st.info("No categories detected for this event; you can still save participants (category field will be blank).")
        with st.form(K("form_one")):
            pname = st.text_input("Full name", key=K(f"one_name_{current_cat}"))
            phone = st.text_input("Phone", key=K(f"one_phone_{current_cat}"))
            email = st.text_input("Email ID", key=K(f"one_email_{current_cat}"))
            grade = st.text_input("Grade / Std", key=K(f"one_grade_{current_cat}"))
            sc = ""
            if subcats:
                sc = st.selectbox("Category", subcats, index=(subcats.index(current_cat) if current_cat in subcats else 0), key=K(f"one_cat_{current_cat}"))
            saved = st.form_submit_button("Save")
        if saved and pname and pname.strip():
            upsert_participant(ev["name"], pname, phone, email, grade, sc); st.success("Saved.")

        st.markdown("**Bulk add**")
        if K("rows") not in st.session_state:
            st.session_state[K("rows")] = 1
        cA, cB, _ = st.columns([1,1,6])
        if cA.button("➕ Add row", key=K("plus")):
            st.session_state[K("rows")] += 1
        if cB.button("➖ Remove row", key=K("minus")):
            st.session_state[K("rows")] = max(1, st.session_state[K("rows")] - 1)
        nrows = st.session_state[K("rows")]
        bucket = []
        for i in range(nrows):
            with st.expander(f"Row #{i+1} — {ev['name']}"):
                bn = st.text_input("Full name", key=K(f"bn_{i}"))
                bp = st.text_input("Phone", key=K(f"bp_{i}"))
                be = st.text_input("Email", key=K(f"be_{i}"))
                bg = st.text_input("Grade", key=K(f"bg_{i}"))
                bs = ""
                if subcats:
                    bs = st.selectbox("Category", subcats, index=0, key=K(f"bs_{i}"))
                bucket.append((bn,bp,be,bg,bs))
        if st.button("Save all", key=K("saveall")):
            cnt = 0
            for (bn,bp,be,bg,bs) in bucket:
                if bn and bn.strip():
                    upsert_participant(ev["name"], bn, bp, be, bg, bs); cnt += 1
            st.success(f"Saved {cnt} participant(s).")

        if plist:
            rm = st.selectbox("Remove participant (current category view)", ["--"]+[p["name"] for p in plist], key=K("rm"))
            if rm != "--":
                remove_participant(ev["name"], rm, sub_filter if (subcats and sub_filter!="All") else "")
                st.warning(f"Removed {rm}")
    else:
        st.info("Only admins can edit participants.")

    # Roster & messaging per participant
    for idx, p in enumerate(plist, start=1):
        c1, c2, c3, c4 = st.columns([2,2,1,3])
        with c1:
            st.write(f"{idx}. **{p['name']}** — _{p.get('subcat') or '(no category)'}_")
            st.caption(f"Grade: {p.get('grade','')}")
        with c2:
            st.write(p.get("phone","")); st.caption(p.get("email",""))
        with c3:
            if is_admin:
                if st.button("Message", key=K(f"msgbtn_{idx}")):
                    st.session_state[K(f"open_thread_{idx}")] = True
        with c4:
            thread = get_thread(ekey(ev["name"]), p["name_key"])
            if thread:
                last = thread[-1]
                st.caption(f"Last: {last['from']}: {last['text'][:60]}{'...' if len(last['text'])>60 else ''}")

        open_key = st.session_state.get(K(f"open_thread_{idx}"), False)
        is_self = participant_name and nkey(participant_name)==p["name_key"]
        if open_key or is_self:
            with st.expander(f"Thread with {p['name']} — {ev['name']}"):
                thread = get_thread(ekey(ev["name"]), p["name_key"])
                if not thread:
                    st.caption("No messages yet.")
                else:
                    for m in thread:
                        dir_txt = (f"{m['from']} → You" if m["to_key"]==p["name_key"] else f"{m['from']} → Admins")
                        st.markdown(f"**{m['timestamp']}** — {dir_txt}")
                        st.write(m["text"])
                if is_self:
                    msg = st.text_area("Your message to Admins", key=K(f"pmsg_{idx}"))
                    if st.button("Send", key=K(f"psend_{idx}")) and msg.strip():
                        send_message("Admins", participant_name, ev["name"], msg.strip(), to_role="admin")
                        st.success("Sent.")
                if is_admin and admin_name:
                    reply = st.text_area("Admin message", key=K(f"amsg_{idx}"))
                    if st.button("Send to participant", key=K(f"asend_{idx}")) and reply.strip():
                        send_message(p["name"], admin_name, ev["name"], reply.strip(), to_role="participant")
                        st.success("Sent.")
                        st.session_state[K(f"open_thread_{idx}")] = False

    if participant_name:
        my_rows = [p for p in event_participants(ev["name"]) if p["name_key"]==nkey(participant_name)]
        if my_rows:
            st.subheader("Your Event Control")
            now = datetime.now()
            if sdt and now >= sdt and (not edt or now <= edt + timedelta(hours=1)):
                atv = st.checkbox("I am at the venue", key=K("venue"))
                if st.button("Mark event completed", key=K("done")):
                    s = load_store()
                    s["completions"].append({
                        "event": ev["name"], "event_key": ekey(ev["name"]),
                        "name": participant_name, "name_key": nkey(participant_name),
                        "timestamp": datetime.now().isoformat(), "at_venue": bool(atv)
                    })
                    save_store(s); st.success("Marked completed.")
            else:
                if sdt:
                    mins = int((sdt - now).total_seconds() // 60)
                    if 0 < mins <= 30: st.warning("⏰ Your event starts in 30 minutes or less.")
                    if 0 < mins <= 10: st.error("⏰ Your event starts in 10 minutes — are you at the venue?")

# ----- Tabs -----
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🔎 Search", "🗓️ Timeline", "🧑‍🎓 Your Events", "✉️ Messages", "🟢 Online", "🗂️ Admin Data"])

with tab1:
    kind = st.radio("Search for", ["Events","Participants"], horizontal=True, key="search_kind")
    if kind == "Events":
        q = st.text_input("Search events/teachers/keywords", key="search_events_q")
        cats = ["All"] + sorted({ev.get("category","") for ev in EVENTS})
        c1, c2 = st.columns([1,1])
        with c1: pick_cat = st.selectbox("Filter by category", cats, key="flt_cat_global")
        with c2: pick_day = st.selectbox("Filter by day", ["All","Day 1 (Fri 26 Sep)","Day 2 (Sat 27 Sep)"], key="flt_day_global")
        nq = norm(q or "")
        res = []
        for ev in EVENTS:
            hay = " ".join([ev.get("name",""), ev.get("category",""), ev.get("age_category",""),
                            ev.get("teacher_in_charge",""), ev.get("brochure_block","")]).lower()
            ok = True if not nq else all(tok in hay for tok in nq.split())
            if pick_cat!="All": ok &= (ev.get("category","")==pick_cat)
            if pick_day!="All":
                ds = (ev.get("date") or ev.get("date_info_duty","")).upper()
                if pick_day.endswith("26 Sep"): ok &= ("FRIDAY" in ds or "26" in ds)
                else: ok &= ("SATURDAY" in ds or "27" in ds)
            if ok: res.append(ev)
        st.write(f"Found {len(res)} event(s).")
        for ev in res:
            with st.container(border=True):
                render_event_card(ev, scope="search", is_admin=is_admin, participant_name=current_user, admin_name=admin_name)
    else:
        pq = st.text_input("Search participant name", key="search_participant_global").strip()
        s = load_store()
        hits = [p for p in s["participants"] if norm(pq) in p["name_key"]] if pq else []
        ev_keys = {p["event_key"] for p in hits}
        res = [EVENTS_BY_KEY[k] for k in ev_keys if k in EVENTS_BY_KEY]
        st.write(f"Found {len(res)} event(s).")
        for ev in res:
            with st.container(border=True):
                render_event_card(ev, scope="partsearch", is_admin=is_admin, participant_name=current_user, admin_name=admin_name)

with tab2:
    st.subheader("Event Timeline")
    items = []
    for ev in EVENTS:
        sdt, edt = parse_datetime_fields(ev)
        items.append((sdt or datetime(2099,1,1), edt, ev))
    items.sort(key=lambda x: x[0])
    for sdt, edt, ev in items:
        with st.container(border=True):
            render_event_card(ev, scope="timeline", is_admin=is_admin, participant_name=current_user, admin_name=admin_name)

with tab3:
    if not current_user:
        st.info("Enter your name above.")
    else:
        nk = nkey(current_user)
        my_events = [EVENTS_BY_KEY[p["event_key"]] for p in load_store()["participants"] if p["name_key"]==nk and p["event_key"] in EVENTS_BY_KEY]
        if not my_events: st.warning("No events assigned to your name yet.")
        for ev in my_events:
            with st.container(border=True):
                render_event_card(ev, scope="your", is_admin=False, participant_name=current_user)

with tab4:
    st.subheader("Messages")
    if current_user and not is_admin:
        nk = nkey(current_user)
        msgs = [m for m in load_store()["messages"] if (m["to_key"]==nk or m["from_key"]==nk)]
        if not msgs:
            st.caption("No messages yet.")
        else:
            for m in sorted(msgs, key=lambda x: x["timestamp"]):
                is_me = (m["from_key"]==nk)
                left, right = st.columns([6,6])
                bubble = f"**{m['from']}** · {m['timestamp']}\\n\\n{m['text']}"
                style = ("background-color:#e7fbe7;border:1px solid #cdeccd;border-radius:12px;padding:10px;"
                         if is_me else
                         "background-color:#f1f0f0;border:1px solid #e0e0e0;border-radius:12px;padding:10px;")
                html = f"<div style='{style}'>{bubble}</div>"
                if is_me:
                    with right: st.markdown(html, unsafe_allow_html=True)
                else:
                    with left: st.markdown(html, unsafe_allow_html=True)
            st.divider()
        my_ev_names = sorted({EVENTS_BY_KEY[p['event_key']]['name'] for p in load_store()['participants'] if p['name_key']==nk and p['event_key'] in EVENTS_BY_KEY})
        if my_ev_names:
            ev_pick = st.selectbox("Choose event", my_ev_names, key="participant_compose_event")
            msg = st.text_area("Write a message to Admins", key="participant_compose_text")
            if st.button("Send", key="participant_send_btn") and msg.strip():
                send_message("Admins", current_user, ev_pick, msg.strip(), to_role="admin")
                st.success("Sent to Admins.")
    else:
        who = st.text_input("Filter by participant (optional)", key="msg_admin_filter_name").strip().lower()
        evf = st.text_input("Filter by event (optional)", key="msg_admin_filter_event").strip().lower()
        msgs = load_store()["messages"]
        for m in sorted(msgs, key=lambda x: x["timestamp"], reverse=True):
            pn = (m.get("to","")+" "+m.get("from","")).lower()
            if who and who not in pn: continue
            if evf and evf not in m.get("event","").lower(): continue
            st.markdown(f"**{m['timestamp']}** — To *{m['to']}* from **{m['from']}** — **{m['event']}**")
            st.write(m["text"]); st.divider()

with tab5:
    st.subheader("Currently Online (last 5 minutes)")
    now = datetime.now()
    online = []
    for s in load_store().get("sessions", []):
        try:
            if (now - datetime.fromisoformat(s["last_seen"])) <= timedelta(minutes=5):
                online.append(s)
        except:
            pass
    if not online: st.caption("No one online.")
    for s in online:
        st.markdown(f"- **{s['name']}** ({s['role']}) — *last seen {s['last_seen']}*")

with tab6:
    if not is_admin:
        st.info("Admin only.")
    else:
        st.markdown("**Download participants (CSV)**")
        data = load_store()["participants"]
        if data:
            df = pd.DataFrame(data)[["event","name","phone","email","grade","subcat"]]
            buf = io.StringIO(); df.to_csv(buf, index=False)
            st.download_button("Download CSV", buf.getvalue().encode(), file_name="participants.csv", mime="text/csv", key="dl_csv")
        else:
            st.caption("No participants saved yet.")
        # Clean per-event report with exact headers
        data = load_store()["participants"]
        rows = []
        for p in data:
            ev = EVENTS_BY_KEY.get(p.get("event_key"), {"name": p.get("event",""), "teacher_in_charge": ""})
            rows.append({
                "Event": ev["name"],
                "Teacher": ev.get("teacher_in_charge",""),
                "Category": (p.get("subcat") or ""),
                "Participant Name": p.get("name",""),
                "Email": p.get("email",""),
                "Phone": p.get("phone",""),
                "Grade": p.get("grade","")
            })
        if rows:
            out_rows = []
            for r in rows:
                grade = (r.get("Grade") or "").strip()
                std, div = "", ""
                if grade:
                    parts = grade.split()
                    if parts:
                        std = parts[0]
                        div = " ".join(parts[1:]) if len(parts)>1 else ""
                ev = r.get("Event","")
                date_txt = EVENTS_BY_KEY.get(ekey(ev), {}).get("date") or EVENTS_BY_KEY.get(ekey(ev), {}).get("date_info_duty","")
                out_rows.append({
                    "NAME OF THE EVENT": ev,
                    "TEACHER IN CHARGE": r.get("Teacher",""),
                    "NAME OF PARTICIPANTS": r.get("Participant Name",""),
                    "EMAIL ID OF PARTICIPANTS": r.get("Email",""),
                    "PHONE NUMBER": r.get("Phone",""),
                    "STD": std,
                    "DIV": div,
                    "DATES": date_txt,
                    "CATEGORY": r.get("Category","")
                })
            rep_df = pd.DataFrame(out_rows, columns=["NAME OF THE EVENT","TEACHER IN CHARGE","NAME OF PARTICIPANTS","EMAIL ID OF PARTICIPANTS","PHONE NUMBER","STD","DIV","DATES","CATEGORY"])
            buf2 = io.StringIO(); rep_df.to_csv(buf2, index=False)
            st.download_button("Download clean per-event report (CSV)", buf2.getvalue().encode(), file_name="event_participants_report.csv", mime="text/csv", key="dl_report")
