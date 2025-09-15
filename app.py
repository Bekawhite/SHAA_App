# SHA_Connect.py
# Kisumu County Referral Hospital - SHA Awareness Platform
# Fully integrated: multilingual UI, FAQs & chatbot (OpenAI optional),
# SMS/Voice (Twilio optional), persistent local caching, outbox queue, analytics, partners, feedback, reminders, dashboard.
#
# Usage:
# 1. put this file in a folder
# 2. create a ./data folder (the app will create it automatically)
# 3. set credentials in Streamlit secrets or environment variables:
#    - For Twilio (optional): in Streamlit secrets
#        [twilio]
#        account_sid = "ACxxxxx"
#        auth_token = "xxxx"
#        from_number = "+1...."
#    - For OpenAI (optional): in Streamlit secrets
#        [openai]
#        api_key = "sk-..."
#
# Run: streamlit run SHA_Connect.py

import streamlit as st
import pandas as pd
import numpy as np
import datetime
import os
import json
import traceback

# Optional dependencies (import safely)
try:
    from twilio.rest import Client as TwilioClient
except Exception:
    TwilioClient = None

try:
    import openai
except Exception:
    openai = None

try:
    from googletrans import Translator as GTTranslator
except Exception:
    GTTranslator = None

# ---------------------------
# Configuration & data paths
# ---------------------------
DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)

PARTNERS_FILE = os.path.join(DATA_DIR, "partners.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "message_logs.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.json")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")
OUTBOX_FILE = os.path.join(DATA_DIR, "outbox.json")

# ---------------------------
# Helpers: JSON persistence
# ---------------------------
def save_df_to_file(df: pd.DataFrame, path: str):
    try:
        # to_json with force_ascii=False preserves unicode (local languages)
        df.to_json(path, orient="records", force_ascii=False, date_format="iso")
    except Exception:
        # fallback using python json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)

def load_df_from_file(path: str, columns=None):
    if not os.path.isfile(path):
        if columns:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame()
    try:
        df = pd.read_json(path, orient="records")
        if columns:
            # ensure expected columns exist
            for c in columns:
                if c not in df.columns:
                    df[c] = ""
            return df[columns]
        return df
    except Exception:
        try:
            with open(path, "r", encoding="utf-8") as f:
                records = json.load(f)
            df = pd.DataFrame(records)
            if columns:
                for c in columns:
                    if c not in df.columns:
                        df[c] = ""
                return df[columns]
            return df
        except Exception:
            return pd.DataFrame()

# ---------------------------
# App UI / startup
# ---------------------------
st.set_page_config(page_title="SHA Connect — Kisumu County Referral Hospital", layout="wide")
st.title("SHA Connect — Kisumu County Referral Hospital")
st.markdown("An awareness & outreach platform (Swahili, Luo, Luhya, English).")

# Sidebar navigation
st.sidebar.title("Navigation")
PAGES = [
    "Home",
    "FAQs & Chatbot",
    "Multilingual Messages",
    "Outreach Partners",
    "Community Feedback",
    "Notifications & Reminders",
    "Campaign Dashboard",
    "Outbox",
    "Settings"
]
choice = st.sidebar.radio("Go to:", PAGES)

language_options = ["English", "Swahili", "Luo", "Luhya"]
selected_language = st.sidebar.selectbox("Choose Language:", language_options)

# ---------------------------
# Load persisted data into session state
# ---------------------------
if "partners_df" not in st.session_state:
    st.session_state.partners_df = load_df_from_file(PARTNERS_FILE, columns=["Name", "Role", "Language", "Contact", "Campaign Assigned"])

if "message_logs" not in st.session_state:
    st.session_state.message_logs = load_df_from_file(MESSAGES_FILE, columns=["Recipient", "Message", "Language", "Date Sent", "Type", "Status"])

if "feedback_df" not in st.session_state:
    st.session_state.feedback_df = load_df_from_file(FEEDBACK_FILE, columns=["Name", "Message", "Language", "Date Submitted"])

if "reminders_df" not in st.session_state:
    st.session_state.reminders_df = load_df_from_file(REMINDERS_FILE, columns=["Task", "Due Date", "Assigned To", "Status"])

if "outbox_df" not in st.session_state:
    st.session_state.outbox_df = load_df_from_file(OUTBOX_FILE, columns=["Recipient", "Message", "Language", "Date Created", "Type", "Attempts"])

# ---------------------------
# Translation utilities and custom translations
# ---------------------------
# Use GoogleTrans when available, else rely on custom dictionary / pass-through.
gt_translator = GTTranslator() if GTTranslator else None

custom_translations = {
    "Luo": {
        "What is SHA?": "SHA en Social Health Authority, ma orit gi dhok yi mondo giko gi bedo mag dhok.",
        "How can I register for SHA?": "Inyalo registr kendo e health center maduong' gi e SHA portal.",
        "Which services are covered?": "SHA en giko mag preventive care, maternal care, kod treatments ma nyaka.",
        "Thank you for your feedback!": "Awuoyo gi nyalo walo!"
    },
    "Luhya": {
        "What is SHA?": "SHA ni Social Health Authority, ebuya amagara netaweire.",
        "How can I register for SHA?": "Olwikhilire kuhealth center oba e SHA portal.",
        "Which services are covered?": "SHA ibuyire preventive care, maternal care, ne essential treatments.",
        "Thank you for your feedback!": "Webale muno okhu"
    }
}

def safe_translate(text: str, lang: str) -> str:
    """
    Robust translation helper:
    - If lang is English: return text
    - If custom translation exists (Luo/Luhya) and exact phrase matches: use it
    - If googletrans available and lang == Swahili: translate via googletrans
    - On any error: return original text
    """
    if not text:
        return text
    # exact-match custom translations for Luo/Luhya
    if lang in ("Luo", "Luhya"):
        return custom_translations.get(lang, {}).get(text, text)
    if lang == "English":
        return text
    if lang == "Swahili":
        if gt_translator:
            try:
                return gt_translator.translate(text, dest="sw").text
            except Exception:
                return text
        else:
            return text
    return text

# ---------------------------
# FAQs
# ---------------------------
faqs = {
    "What is SHA?": "SHA stands for Social Health Authority, which provides health services and benefits.",
    "How can I register for SHA?": "You can register at your nearest health center or via the SHA portal.",
    "Which services are covered?": "SHA covers preventive care, maternal care, and essential treatments."
}

# ---------------------------
# Twilio + OpenAI configuration helpers
# ---------------------------
def twilio_configured() -> bool:
    # prefer st.secrets; fall back to env
    has_secrets = ("twilio" in st.secrets and "account_sid" in st.secrets["twilio"] and
                   "auth_token" in st.secrets["twilio"] and "from_number" in st.secrets["twilio"])
    if has_secrets:
        return True
    # fallback to env
    return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN") and os.getenv("TWILIO_PHONE_NUMBER"))

def get_twilio_client():
    if not twilio_configured():
        return None
    try:
        if "twilio" in st.secrets:
            sid = st.secrets["twilio"]["account_sid"]
            token = st.secrets["twilio"]["auth_token"]
        else:
            sid = os.getenv("TWILIO_ACCOUNT_SID")
            token = os.getenv("TWILIO_AUTH_TOKEN")
        if TwilioClient is None:
            return None
        return TwilioClient(sid, token)
    except Exception:
        return None

def openai_configured() -> bool:
    return ("openai" in st.secrets and "api_key" in st.secrets["openai"]) or bool(os.getenv("OPENAI_API_KEY"))

def configure_openai_api():
    if not openai_configured() or openai is None:
        return False
    try:
        if "openai" in st.secrets:
            openai.api_key = st.secrets["openai"]["api_key"]
        else:
            openai.api_key = os.getenv("OPENAI_API_KEY")
        return True
    except Exception:
        return False

# Safe Twilio send functions (wrap in try/except)
def safe_send_sms(to_number: str, body: str):
    client = get_twilio_client()
    if client is None:
        return False, "Twilio not configured or library missing."
    try:
        from_number = st.secrets["twilio"]["from_number"] if "twilio" in st.secrets else os.getenv("TWILIO_PHONE_NUMBER")
        msg = client.messages.create(body=body, from_=from_number, to=to_number)
        return True, getattr(msg, "sid", "sent")
    except Exception as e:
        return False, str(e)

def safe_make_call(to_number: str, text_to_say: str):
    client = get_twilio_client()
    if client is None:
        return False, "Twilio not configured or library missing."
    try:
        from_number = st.secrets["twilio"]["from_number"] if "twilio" in st.secrets else os.getenv("TWILIO_PHONE_NUMBER")
        call = client.calls.create(twiml=f'<Response><Say>{text_to_say}</Say></Response>', from_=from_number, to=to_number)
        return True, getattr(call, "sid", "call-initiated")
    except Exception as e:
        return False, str(e)

# ---------------------------
# Outbox management
# ---------------------------
def add_to_outbox(recipient, message, language, msg_type="sms"):
    row = {
        "Recipient": recipient,
        "Message": message,
        "Language": language,
        "Date Created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Type": msg_type,
        "Attempts": 0
    }
    st.session_state.outbox_df = pd.concat([st.session_state.outbox_df, pd.DataFrame([row])], ignore_index=True)
    save_df_to_file(st.session_state.outbox_df, OUTBOX_FILE)
    st.success("Message queued to outbox.")

def process_outbox(max_attempts=3):
    if st.session_state.outbox_df.empty:
        st.info("Outbox is empty.")
        return []
    results = []
    # iterate over a copy to allow deletions
    for idx, row in st.session_state.outbox_df.copy().iterrows():
        attempts = int(row.get("Attempts", 0))
        if attempts >= max_attempts:
            results.append((idx, False, "max attempts reached"))
            continue
        recipient = row["Recipient"]
        message = row["Message"]
        msg_type = row.get("Type", "sms")
        language = row.get("Language", "English")
        if msg_type == "sms":
            ok, info = safe_send_sms(recipient, message)
        else:
            ok, info = safe_make_call(recipient, message)
        # update attempts
        st.session_state.outbox_df.at[idx, "Attempts"] = attempts + 1
        if ok:
            # log into message_logs
            sent_row = {
                "Recipient": recipient,
                "Message": message,
                "Language": language,
                "Date Sent": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Type": msg_type,
                "Status": "Sent"
            }
            st.session_state.message_logs = pd.concat([st.session_state.message_logs, pd.DataFrame([sent_row])], ignore_index=True)
            # remove from outbox
            st.session_state.outbox_df = st.session_state.outbox_df.drop(idx)
            results.append((idx, True, info))
        else:
            results.append((idx, False, info))
    # persist changes
    save_df_to_file(st.session_state.outbox_df, OUTBOX_FILE)
    save_df_to_file(st.session_state.message_logs, MESSAGES_FILE)
    return results

# ---------------------------
# Utility: persist all main tables
# ---------------------------
def persist_all():
    save_df_to_file(st.session_state.partners_df, PARTNERS_FILE)
    save_df_to_file(st.session_state.message_logs, MESSAGES_FILE)
    save_df_to_file(st.session_state.feedback_df, FEEDBACK_FILE)
    save_df_to_file(st.session_state.reminders_df, REMINDERS_FILE)
    save_df_to_file(st.session_state.outbox_df, OUTBOX_FILE)

# ---------------------------
# Pages / Functionality
# ---------------------------
if choice == "Home":
    st.subheader("Home")
    st.markdown("""
    - Learn about SHA services.
    - Access resources and community outreach events.
    - Use the sidebar to navigate: FAQs & Chatbot, Messaging, Partners, Feedback, Reminders, Dashboard.
    """)
    st.info("App caches data locally in ./data — this helps in areas with intermittent internet. Use the Outbox page to re-send queued messages when network is back.")

# ---------------------------
# FAQs & Chatbot
# ---------------------------
elif choice == "FAQs & Chatbot":
    st.subheader("FAQs")
    for q, a in faqs.items():
        with st.expander(safe_translate(q, selected_language)):
            st.write(safe_translate(a, selected_language))

    st.subheader("Ask the Chatbot")
    user_input = st.text_input("Type your question here:")
    if st.button("Get Answer"):
        if not user_input:
            st.warning("Please enter a question.")
        else:
            # Prefer OpenAI if configured and available
            if openai and configure_openai_api():
                try:
                    # Use ChatCompletion (gpt-3.5-turbo or gpt-4 depending on user)
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "system", "content": "You are a helpful assistant for SHA health services in Kisumu. Keep answers short and local-language friendly."},
                                  {"role": "user", "content": user_input}]
                    )
                    answer = response.choices[0].message.content.strip()
                    st.markdown(f"**Chatbot (AI) Response:** {safe_translate(answer, selected_language)}")
                except Exception as e:
                    st.error(f"OpenAI error: {e}")
                    # fallback to simple keyword-based reply
                    fallback = "Sorry, I couldn't fetch an AI response. Here is a simple answer attempt."
                    for q, a in faqs.items():
                        if user_input.lower() in q.lower() or user_input.lower() in a.lower():
                            fallback = a
                            break
                    st.markdown(f"**Chatbot (Fallback):** {safe_translate(fallback, selected_language)}")
            else:
                # simple keyword-based chatbot
                response = "Sorry, I don't have an answer for that yet."
                for q, a in faqs.items():
                    if user_input.lower() in q.lower() or user_input.lower() in a.lower():
                        response = a
                        break
                st.markdown(f"**Chatbot Response:** {safe_translate(response, selected_language)}")

# ---------------------------
# Multilingual Messages (SMS/Voice)
# ---------------------------
elif choice == "Multilingual Messages":
    st.subheader("Send Multilingual Messages")
    if not twilio_configured() or TwilioClient is None:
        st.warning("Twilio not configured or library missing. Messages will be queued to Outbox if 'Send' is attempted. To enable live SMS/Voice, set Twilio credentials in Streamlit secrets or environment variables and install twilio library.")
    recipient = st.text_input("Recipient phone number (with country code):")
    msg_text = st.text_area("Message text")
    col1, col2 = st.columns(2)
    with col1:
        msg_type = st.selectbox("Message Type", ["sms", "voice"])
    with col2:
        msg_lang = st.selectbox("Message Language", language_options, index=language_options.index(selected_language))
    if st.button("Send Now"):
        if not recipient or not msg_text:
            st.warning("Please enter recipient and message.")
        else:
            translated = safe_translate(msg_text, msg_lang)
            if msg_type == "sms":
                ok, info = safe_send_sms(recipient, translated) if twilio_configured() and TwilioClient else (False, "Twilio not configured")
                if ok:
                    st.success(f"SMS sent: {info}")
                    log_row = {
                        "Recipient": recipient,
                        "Message": translated,
                        "Language": msg_lang,
                        "Date Sent": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Type": "sms",
                        "Status": "Sent"
                    }
                    st.session_state.message_logs = pd.concat([st.session_state.message_logs, pd.DataFrame([log_row])], ignore_index=True)
                    save_df_to_file(st.session_state.message_logs, MESSAGES_FILE)
                else:
                    st.error(f"Send failed: {info} — queued to Outbox.")
                    add_to_outbox(recipient, translated, msg_lang, msg_type="sms")
            else:
                ok, info = safe_make_call(recipient, translated) if twilio_configured() and TwilioClient else (False, "Twilio not configured")
                if ok:
                    st.success(f"Voice call initiated: {info}")
                    log_row = {
                        "Recipient": recipient,
                        "Message": translated,
                        "Language": msg_lang,
                        "Date Sent": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Type": "voice",
                        "Status": "Sent"
                    }
                    st.session_state.message_logs = pd.concat([st.session_state.message_logs, pd.DataFrame([log_row])], ignore_index=True)
                    save_df_to_file(st.session_state.message_logs, MESSAGES_FILE)
                else:
                    st.error(f"Voice send failed: {info} — queued to Outbox.")
                    add_to_outbox(recipient, translated, msg_lang, msg_type="voice")
    st.markdown("#### Recent messages")
    if not st.session_state.message_logs.empty:
        st.dataframe(st.session_state.message_logs.sort_values("Date Sent", ascending=False).head(15))
    else:
        st.info("No messages logged yet.")

# ---------------------------
# Outreach Partners
# ---------------------------
elif choice == "Outreach Partners":
    st.subheader("Community & Influencer Outreach")
    with st.expander("Add New Partner"):
        name = st.text_input("Partner Name")
        role = st.selectbox("Role", ["Community Leader", "Influencer", "Volunteer"])
        langs = st.multiselect("Languages Spoken", language_options)
        contact = st.text_input("Contact Info (phone/email)")
        campaign = st.text_input("Campaign Assigned")
        if st.button("Add Partner"):
            if not name:
                st.warning("Partner name is required.")
            else:
                new_partner = {
                    "Name": name,
                    "Role": role,
                    "Language": ", ".join(langs),
                    "Contact": contact,
                    "Campaign Assigned": campaign
                }
                st.session_state.partners_df = pd.concat([st.session_state.partners_df, pd.DataFrame([new_partner])], ignore_index=True)
                save_df_to_file(st.session_state.partners_df, PARTNERS_FILE)
                st.success(f"Partner {name} added.")
    st.markdown("#### Registered Partners")
    if not st.session_state.partners_df.empty:
        st.dataframe(st.session_state.partners_df)
    else:
        st.info("No partners registered yet.")
    search = st.text_input("Search partner by name")
    if search:
        filtered = st.session_state.partners_df[st.session_state.partners_df["Name"].str.contains(search, case=False, na=False)]
        st.dataframe(filtered)

# ---------------------------
# Community Feedback
# ---------------------------
elif choice == "Community Feedback":
    st.subheader("Community Feedback")
    with st.expander("Submit Feedback"):
        fname = st.text_input("Your Name")
        fmsg = st.text_area("Your Feedback")
        flang = st.selectbox("Language", language_options, index=language_options.index(selected_language) if selected_language in language_options else 0)
        if st.button("Submit Feedback"):
            if not fname or not fmsg:
                st.warning("Please enter your name and feedback.")
            else:
                new_fb = {
                    "Name": fname,
                    "Message": fmsg,
                    "Language": flang,
                    "Date Submitted": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                st.session_state.feedback_df = pd.concat([st.session_state.feedback_df, pd.DataFrame([new_fb])], ignore_index=True)
                save_df_to_file(st.session_state.feedback_df, FEEDBACK_FILE)
                conf = safe_translate("Thank you for your feedback!", flang)
                st.success(conf)
    st.markdown("#### Feedback Received")
    if not st.session_state.feedback_df.empty:
        st.dataframe(st.session_state.feedback_df.sort_values("Date Submitted", ascending=False))
        st.markdown("#### Feedback Analytics (by language)")
        st.bar_chart(st.session_state.feedback_df["Language"].value_counts())
    else:
        st.info("No feedback yet.")

# ---------------------------
# Notifications & Reminders
# ---------------------------
elif choice == "Notifications & Reminders":
    st.subheader("Staff Notifications & Reminders")
    with st.expander("Add New Reminder"):
        task = st.text_input("Task Description")
        due_date = st.date_input("Due Date", datetime.date.today())
        assigned_to = st.text_input("Assigned To")
        if st.button("Add Reminder"):
            if not task or not assigned_to:
                st.warning("Please enter task and assignee.")
            else:
                new_rem = {
                    "Task": task,
                    "Due Date": due_date.strftime("%Y-%m-%d"),
                    "Assigned To": assigned_to,
                    "Status": "Pending"
                }
                st.session_state.reminders_df = pd.concat([st.session_state.reminders_df, pd.DataFrame([new_rem])], ignore_index=True)
                save_df_to_file(st.session_state.reminders_df, REMINDERS_FILE)
                st.success(f"Reminder for '{task}' added.")
    st.markdown("#### Upcoming Reminders")
    if not st.session_state.reminders_df.empty:
        st.dataframe(st.session_state.reminders_df)
        pending_tasks = st.session_state.reminders_df[st.session_state.reminders_df["Status"] == "Pending"]["Task"].tolist()
        if pending_tasks:
            selected_task = st.selectbox("Mark completed", pending_tasks)
            if st.button("Mark Completed"):
                st.session_state.reminders_df.loc[st.session_state.reminders_df["Task"] == selected_task, "Status"] = "Completed"
                save_df_to_file(st.session_state.reminders_df, REMINDERS_FILE)
                st.success(f"Task '{selected_task}' marked completed.")
    else:
        st.info("No reminders yet.")

# ---------------------------
# Campaign Dashboard
# ---------------------------
elif choice == "Campaign Dashboard":
    st.subheader("📊 Campaign Dashboard")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Messages Sent")
        if not st.session_state.message_logs.empty:
            st.metric("Total Messages Sent", len(st.session_state.message_logs))
            st.bar_chart(st.session_state.message_logs["Language"].value_counts())
        else:
            st.info("No messages sent yet.")
    with col2:
        st.markdown("### Outreach Partners")
        if not st.session_state.partners_df.empty:
            st.metric("Total Partners", len(st.session_state.partners_df))
            st.bar_chart(st.session_state.partners_df["Role"].value_counts())
        else:
            st.info("No partners added yet.")
    st.markdown("### Community Feedback")
    if not st.session_state.feedback_df.empty:
        st.metric("Total Feedback Received", len(st.session_state.feedback_df))
        st.bar_chart(st.session_state.feedback_df["Language"].value_counts())
    else:
        st.info("No feedback yet.")
    st.markdown("### Reminders")
    if not st.session_state.reminders_df.empty:
        pending = len(st.session_state.reminders_df[st.session_state.reminders_df["Status"] == "Pending"])
        completed = len(st.session_state.reminders_df[st.session_state.reminders_df["Status"] == "Completed"])
        st.metric("Pending Reminders", pending)
        st.metric("Completed Reminders", completed)
        st.dataframe(st.session_state.reminders_df)
    else:
        st.info("No reminders yet.")

# ---------------------------
# Outbox (queued messages)
# ---------------------------
elif choice == "Outbox":
    st.subheader("Outbox — queued messages waiting for send")
    st.markdown("Messages that failed to send (Twilio errors or offline) appear here. Use 'Process Outbox' when network is available.")
    if not st.session_state.outbox_df.empty:
        st.dataframe(st.session_state.outbox_df)
    else:
        st.info("Outbox is empty.")
    if st.button("Process Outbox (attempt send)"):
        with st.spinner("Processing outbox..."):
            try:
                results = process_outbox()
                if not results:
                    st.info("No messages processed.")
                else:
                    for idx, ok, info in results:
                        if ok:
                            st.success(f"Outbox item {idx} sent: {info}")
                        else:
                            st.error(f"Outbox item {idx} NOT sent: {info}")
            except Exception:
                st.error("Error while processing outbox.")
                st.text(traceback.format_exc())

# ---------------------------
# Settings
# ---------------------------
elif choice == "Settings":
    st.subheader("Settings & Credentials")
    st.markdown("**Twilio:** optional — configure in Streamlit Secrets or environment variables.")
    tw_conf = twilio_configured()
    st.write(f"Twilio configured: {tw_conf}")
    st.markdown("**OpenAI:** optional — configure in Streamlit Secrets or environment variables.")
    st.write(f"OpenAI library installed: {openai is not None}, configured: {openai_configured()}")
    st.markdown("**Local cache path**: `./data`")
    if st.button("Save all data to disk now"):
        persist_all()
        st.success("All data saved.")

# Persist state on every run
persist_all()
