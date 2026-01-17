import streamlit as st
import json
import re
import pandas as pd
import io
from datetime import datetime, timedelta
from pathlib import Path
import time

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
APP_TITLE = "Cynosure 2025 Portal"
ADMIN_PASSWORD = "vxxxk"  # Change as needed
DATA_FILE = Path(__file__).with_name("cynosure_events.json")
STORE_FILE = Path(__file__).with_name("participants_store.json")

st.set_page_config(
    page_title=APP_TITLE, 
    layout="wide", 
    page_icon="🏆",
    initial_sidebar_state="expanded"
)

# Custom CSS for "WhatsApp" feel and clean UI
st.markdown("""
<style>
    .stChatMessage { padding: 10px; border-radius: 10px; }
    .stChatInput { bottom: 20px; }
    div[data-testid="stMetricValue"] { font-size: 1.2rem; }
    .status-badge { padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8em;}
    .status-ongoing { background-color: #ffeeba; color: #856404; }
    .status-completed { background-color: #d4edda; color: #155724; }
    .status-upcoming { background-color: #cce5ff; color: #004085; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# DATA LAYER (ROBUST)
# ==========================================

def load_events():
    """Loads static event data."""
    if not DATA_FILE.exists():
        st.error("❌ Critical: 'cynosure_events.json' not found.")
        st.stop()
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return data.get("events", [])
    except json.JSONDecodeError:
        st.error("❌ Critical: Event file is corrupted.")
        st.stop()

def load_store():
    """Loads dynamic participant/message data."""
    if not STORE_FILE.exists():
        default_data = {"participants": [], "messages": [], "sessions": [], "updated_at": datetime.now().isoformat()}
        STORE_FILE.write_text(json.dumps(default_data, indent=2), encoding="utf-8")
        return default_data
    try:
        return json.loads(STORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"participants": [], "messages": [], "sessions": []}

def save_store(data):
    """Saves dynamic data atomically."""
    data["updated_at"] = datetime.now().isoformat()
    STORE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# ==========================================
# UTILITIES
# ==========================================

def normalize_key(text):
    """Creates a consistent key for searching/linking."""
    if not text: return ""
    return re.sub(r"\s+", " ", text.strip().lower())

def get_event_status(ev):
    """Calculates event status based on date/time strings."""
    # This assumes a simplified parsing logic for demonstration. 
    # Real logic relies on strict date formats in JSON.
    date_str = ev.get("date") or ev.get("date_info_duty", "")
    time_str = ev.get("time", "")
    
    # Simple heuristic for demo purposes
    full_str = f"{date_str} {time_str}".upper()
    now = datetime.now()
    
    # In a real scenario, parse exact datetimes. Here we return generic states.
    if "COMPLETED" in full_str: return "Completed", "status-completed"
    return "Upcoming", "status-upcoming" # Default fallback

def extract_categories(brochure_text):
    """Smartly extracts Age/Gender categories from brochure text."""
    if not brochure_text: return []
    cats = []
    text = brochure_text.replace("\n", " ")
    
    # 1. Look for explicit "Age Category: I. ... II. ..."
    age_match = re.search(r"Age\s*Category\s*[:\-]\s*(.*?)((Duration|Venue|Rules)|$)", text, re.IGNORECASE)
    if age_match:
        segment = age_match.group(1)
        # Split by roman numerals
        parts = re.split(r'(?=[IVX]+\.)', segment)
        for p in parts:
            if p.strip():
                clean = p.strip(" .,-")
                if len(clean) > 3:
                    cats.append(clean)

    # 2. Look for Gender
    if re.search(r'\b(Boys|Girls)\s+Team', text, re.IGNORECASE):
        if "Boys" not in cats: cats.append("Boys Team")
        if "Girls" not in cats: cats.append("Girls Team")
    
    return list(set(cats)) if cats else ["General"]

# ==========================================
# MESSAGING ENGINE
# ==========================================

def send_message(sender, receiver, content, event_context="General"):
    store = load_store()
    msg = {
        "timestamp": datetime.now().isoformat(),
        "from": sender,
        "to": receiver,
        "text": content,
        "event": event_context,
        "read": False
    }
    store["messages"].append(msg)
    save_store(store)

def get_chat_history(user1, user2):
    """Get conversation between two users (or User & Admin)."""
    store = load_store()
    msgs = store.get("messages", [])
    # Filter messages where (From=U1 AND To=U2) OR (From=U2 AND To=U1)
    # Treating 'Admin' as a specific user entity
    history = [
        m for m in msgs 
        if (m["from"] == user1 and m["to"] == user2) or 
           (m["from"] == user2 and m["to"] == user1)
    ]
    return sorted(history, key=lambda x: x["timestamp"])

def get_contacts_for_admin():
    """Returns list of users who have messaged or are participants."""
    store = load_store()
    # Users who sent messages
    msg_users = set([m["from"] for m in store.get("messages", []) if m["to"] == "Admin"])
    # Users who received messages
    rec_users = set([m["to"] for m in store.get("messages", []) if m["from"] == "Admin"])
    # All participants
    all_parts = set([p["name"] for p in store.get("participants", [])])
    
    return sorted(list(msg_users.union(rec_users).union(all_parts)))

# ==========================================
# VIEW: LOGIN
# ==========================================

def render_login():
    st.markdown("<h1 style='text-align: center;'>🔐 Cynosure 2025 Portal</h1>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.container(border=True):
            tabs = st.tabs(["Participant Login", "Admin Login"])
            
            with tabs[0]:
                st.write("Enter your full name as registered.")
                p_name = st.text_input("Full Name", key="login_p_name").strip()
                if st.button("Enter Event Area", type="primary", use_container_width=True):
                    store = load_store()
                    # Fuzzy match check
                    exists = any(normalize_key(p["name"]) == normalize_key(p_name) for p in store["participants"])
                    if exists:
                        # Find exact formatting
                        real_name = next(p["name"] for p in store["participants"] if normalize_key(p["name"]) == normalize_key(p_name))
                        st.session_state["user"] = real_name
                        st.session_state["role"] = "participant"
                        st.rerun()
                    else:
                        st.error("Name not found. Please contact an Admin.")
            
            with tabs[1]:
                a_pass = st.text_input("Password", type="password")
                a_name = st.text_input("Admin Name (for records)")
                if st.button("Admin Access", type="primary", use_container_width=True):
                    if a_pass == ADMIN_PASSWORD and a_name:
                        st.session_state["user"] = f"Admin ({a_name})"
                        st.session_state["role"] = "admin"
                        st.session_state["admin_real_name"] = a_name
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")

# ==========================================
# VIEW: ADMIN DASHBOARD
# ==========================================

def render_admin_dashboard():
    st.sidebar.title(f"🛠️ {st.session_state['user']}")
    menu = st.sidebar.radio("Navigation", ["Manage Participants", "Messaging", "Reports", "Event Overview"])
    
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    EVENTS = load_events()
    STORE = load_store()

    # --- TAB: MANAGE PARTICIPANTS ---
    if menu == "Manage Participants":
        st.title("Manage Participants")
        
        # Select Event
        event_names = [e["name"] for e in EVENTS]
        selected_event_name = st.selectbox("Select Event", event_names)
        selected_event = next(e for e in EVENTS if e["name"] == selected_event_name)
        
        # Context
        cats = extract_categories(selected_event.get("brochure_block", ""))
        
        col1, col2 = st.columns([1, 2])
        
        # Form
        with col1:
            with st.form("add_participant"):
                st.subheader("Add/Edit Participant")
                name = st.text_input("Full Name")
                phone = st.text_input("Phone")
                email = st.text_input("Email")
                grade = st.text_input("Grade/Class")
                category = st.selectbox("Category", cats if cats else ["General"])
                
                submitted = st.form_submit_button("Save Participant")
                if submitted and name:
                    # Update or Append
                    existing = False
                    for p in STORE["participants"]:
                        if p["event"] == selected_event_name and normalize_key(p["name"]) == normalize_key(name):
                            p.update({"phone": phone, "email": email, "grade": grade, "subcat": category})
                            existing = True
                            break
                    if not existing:
                        STORE["participants"].append({
                            "event": selected_event_name,
                            "name": name,
                            "phone": phone,
                            "email": email,
                            "grade": grade,
                            "subcat": category,
                            "added_by": st.session_state["user"]
                        })
                    save_store(STORE)
                    st.success(f"Saved {name} successfully!")
                    time.sleep(1)
                    st.rerun()

        # List
        with col2:
            st.subheader(f"Roster: {selected_event_name}")
            current_roster = [p for p in STORE["participants"] if p["event"] == selected_event_name]
            
            if current_roster:
                df = pd.DataFrame(current_roster)[["name", "grade", "subcat", "phone"]]
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Deletion
                to_delete = st.selectbox("Select to Delete", ["--"] + [p["name"] for p in current_roster])
                if to_delete != "--":
                    if st.button(f"🗑️ Delete {to_delete}"):
                        STORE["participants"] = [p for p in STORE["participants"] if not (p["name"] == to_delete and p["event"] == selected_event_name)]
                        save_store(STORE)
                        st.warning("Deleted.")
                        time.sleep(0.5)
                        st.rerun()
            else:
                st.info("No participants yet.")

    # --- TAB: MESSAGING (WHATSAPP STYLE) ---
    elif menu == "Messaging":
        st.title("💬 Live Messages")
        
        # Sidebar for contacts (Simulated WhatsApp left pane)
        contacts = get_contacts_for_admin()
        
        c_list, c_chat = st.columns([1, 3])
        
        with c_list:
            st.markdown("### Chats")
            search = st.text_input("🔍 Search Contact")
            
            # Filter contacts
            filtered_contacts = [c for c in contacts if search.lower() in c.lower()]
            
            active_contact = st.radio("Select Conversation", filtered_contacts, label_visibility="collapsed")
        
        with c_chat:
            if active_contact:
                st.markdown(f"### 👤 {active_contact}")
                
                # Chat Container
                chat_container = st.container(height=500, border=True)
                history = get_chat_history("Admin", active_contact)
                
                with chat_container:
                    if not history:
                        st.caption("No messages yet. Start the conversation!")
                    
                    for msg in history:
                        role = "assistant" if msg["from"] == "Admin" else "user"
                        avatar = "🛡️" if role == "assistant" else "👤"
                        with st.chat_message(role, avatar=avatar):
                            st.markdown(f"**{msg['timestamp'][11:16]}**")
                            st.write(msg["text"])
                
                # Input
                if prompt := st.chat_input(f"Message {active_contact}..."):
                    send_message("Admin", active_contact, prompt)
                    st.rerun()
            else:
                st.info("Select a contact to start chatting.")

    # --- TAB: REPORTS ---
    elif menu == "Reports":
        st.title("📊 Data Exports")
        
        data = STORE["participants"]
        if not data:
            st.warning("No data found.")
        else:
            df = pd.DataFrame(data)
            
            st.markdown("### Master Participant List")
            st.dataframe(df)
            
            # CSV Download
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV", csv, "cynosure_participants.csv", "text/csv")
            
            st.markdown("### Per Event Breakdown")
            event_groups = df.groupby("event")
            for ev_name, group in event_groups:
                with st.expander(f"{ev_name} ({len(group)})"):
                    st.table(group[["name", "grade", "phone"]])

    # --- TAB: OVERVIEW ---
    elif menu == "Event Overview":
        st.title("📅 Event Schedule")
        for ev in EVENTS:
            with st.expander(f"{ev['name']}"):
                st.json(ev)

# ==========================================
# VIEW: PARTICIPANT DASHBOARD
# ==========================================

def render_participant_dashboard():
    user = st.session_state["user"]
    st.sidebar.title(f"👋 Hi, {user.split()[0]}")
    menu = st.sidebar.radio("Menu", ["My Events", "Chat with Admin", "All Events"])
    
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    EVENTS = load_events()
    STORE = load_store()
    
    my_registrations = [p for p in STORE["participants"] if normalize_key(p["name"]) == normalize_key(user)]

    # --- TAB: MY EVENTS ---
    if menu == "My Events":
        st.title("My Registered Events")
        
        if not my_registrations:
            st.info("You are not registered for any events yet.")
        
        for reg in my_registrations:
            ev_data = next((e for e in EVENTS if e["name"] == reg["event"]), None)
            if ev_data:
                status, badge_class = get_event_status(ev_data)
                
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.subheader(ev_data["name"])
                        st.write(f"📍 **Venue:** {ev_data.get('venue', 'TBD')}")
                        st.write(f"🕒 **Time:** {ev_data.get('time', 'TBD')}")
                        st.caption(f"Registered Category: {reg.get('subcat', 'N/A')}")
                    with c2:
                        st.markdown(f"<div class='status-badge {badge_class}' style='text-align:center'>{status}</div>", unsafe_allow_html=True)
                        if st.button("Download Brochure", key=f"broch_{reg['event']}"):
                            st.code(ev_data.get("brochure_block", "No brochure text."))

    # --- TAB: CHAT ---
    elif menu == "Chat with Admin":
        st.title("💬 Helpdesk / Chat")
        
        chat_container = st.container(height=600, border=True)
        history = get_chat_history(user, "Admin")
        
        with chat_container:
            if not history:
                st.info("👋 Need help? Send a message to the event admins here.")
            
            for msg in history:
                role = "assistant" if msg["from"] == "Admin" else "user"
                avatar = "🛡️" if role == "assistant" else "👤"
                
                with st.chat_message(role, avatar=avatar):
                    st.caption(f"{msg['from']} • {msg['timestamp'][11:16]}")
                    st.write(msg["text"])
        
        if prompt := st.chat_input("Type your message here..."):
            send_message(user, "Admin", prompt)
            st.rerun()

    # --- TAB: ALL EVENTS ---
    elif menu == "All Events":
        st.title("All Events")
        search = st.text_input("Search Events")
        
        for ev in EVENTS:
            if search.lower() in ev["name"].lower() or search == "":
                with st.expander(f"{ev['name']} - {ev.get('category', '')}"):
                    st.write(f"**Teacher:** {ev.get('teacher_in_charge')}")
                    st.write(f"**Date:** {ev.get('date')}")
                    st.caption(ev.get("brochure_block"))

# ==========================================
# MAIN ROUTER
# ==========================================

def main():
    if "user" not in st.session_state:
        render_login()
    else:
        if st.session_state["role"] == "admin":
            render_admin_dashboard()
        else:
            render_participant_dashboard()

if __name__ == "__main__":
    main()
