"""
Notion Task Due Date Reminder
------------------------------
Queries a Notion database for tasks due today or tomorrow (or overdue),
and emails a summary.

Environment variables required (set as GitHub Actions secrets):
  NOTION_TOKEN        - Notion internal integration token
  NOTION_DATABASE_ID  - ID of the database to query
  GMAIL_ADDRESS        - Gmail address to send FROM
  GMAIL_APP_PASSWORD   - Gmail app password (not your normal password)
  NOTIFY_EMAIL          - Email address to send TO (can be same as GMAIL_ADDRESS)

Configuration (edit these to match your database schema):
  DATE_PROPERTY     - name of the Date property in your Notion database
  STATUS_PROPERTY   - name of the Status/Checkbox property
  STATUS_DONE_VALUES - values that count as "done" (so they're excluded)
  TITLE_PROPERTY    - name of the title property (usually "Name")
"""

import os
import smtplib
from datetime import datetime, timedelta, date
from email.mime.text import MIMEText
from notion_client import Client

# ---- Configuration: adjust to match your Notion database ----
DATE_PROPERTY = "Due Date"
STATUS_PROPERTY = "Status"
STATUS_DONE_VALUES = ["Done", "Complete", "Completed"]
TITLE_PROPERTY = "Name"
LOOKAHEAD_DAYS = 1  # 1 = include tomorrow's tasks too. 0 = today only.
INCLUDE_OVERDUE = True

# ---- Load secrets from environment ----
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]


def get_due_tasks():
    notion = Client(auth=NOTION_TOKEN)

    today = date.today()
    cutoff = today + timedelta(days=LOOKAHEAD_DAYS)

    results = notion.databases.query(
        database_id=NOTION_DATABASE_ID,
        filter={
            "property": DATE_PROPERTY,
            "date": {"on_or_before": cutoff.isoformat()},
        },
        sorts=[{"property": DATE_PROPERTY, "direction": "ascending"}],
    )

    tasks = []
    for page in results.get("results", []):
        props = page["properties"]

        # Skip if marked done
        status_prop = props.get(STATUS_PROPERTY, {})
        status_value = None
        if status_prop.get("type") == "status":
            status_value = status_prop["status"]["name"] if status_prop.get("status") else None
        elif status_prop.get("type") == "select":
            status_value = status_prop["select"]["name"] if status_prop.get("select") else None
        elif status_prop.get("type") == "checkbox":
            status_value = "Done" if status_prop.get("checkbox") else None

        if status_value in STATUS_DONE_VALUES:
            continue

        # Get title
        title_prop = props.get(TITLE_PROPERTY, {})
        title_text = "Untitled task"
        if title_prop.get("type") == "title" and title_prop.get("title"):
            title_text = "".join([t["plain_text"] for t in title_prop["title"]])

        # Get date
        date_prop = props.get(DATE_PROPERTY, {})
        due_date_str = None
        if date_prop.get("type") == "date" and date_prop.get("date"):
            due_date_str = date_prop["date"]["start"]

        if due_date_str is None:
            continue

        due_date = datetime.fromisoformat(due_date_str.split("T")[0]).date()

        if due_date < today and not INCLUDE_OVERDUE:
            continue

        tasks.append({
            "title": title_text,
            "due_date": due_date,
            "url": page.get("url", ""),
            "status": status_value or "No status",
        })

    return tasks, today


def categorise(tasks, today):
    overdue, due_today, due_soon = [], [], []
    for t in tasks:
        if t["due_date"] < today:
            overdue.append(t)
        elif t["due_date"] == today:
            due_today.append(t)
        else:
            due_soon.append(t)
    return overdue, due_today, due_soon


def build_email_body(overdue, due_today, due_soon):
    lines = []

    def add_section(title, items):
        if not items:
            return
        lines.append(f"\n{title}")
        lines.append("-" * len(title))
        for t in items:
            lines.append(f"  - {t['title']} (due {t['due_date'].strftime('%a %d %b')}) [{t['status']}]")
            if t["url"]:
                lines.append(f"    {t['url']}")

    add_section(f"OVERDUE ({len(overdue)})", overdue)
    add_section(f"DUE TODAY ({len(due_today)})", due_today)
    add_section(f"DUE SOON ({len(due_soon)})", due_soon)

    if not (overdue or due_today or due_soon):
        return "No tasks due today, tomorrow, or overdue. Nothing to action."

    return "\n".join(lines)


def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [NOTIFY_EMAIL], msg.as_string())


def main():
    tasks, today = get_due_tasks()
    overdue, due_today, due_soon = categorise(tasks, today)

    total = len(overdue) + len(due_today) + len(due_soon)
    subject = f"Notion tasks: {total} due/overdue" if total else "Notion tasks: all clear"

    body = build_email_body(overdue, due_today, due_soon)
    send_email(subject, body)
    print(f"Sent reminder email: {subject}")


if __name__ == "__main__":
    main()
