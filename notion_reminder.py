"""
Notion Task Due Date Reminder
------------------------------
Queries a Notion database for tasks due this week (today through Sunday),
categorises them into today / tomorrow / later this week, and sends an
HTML email summary.

Environment variables (set as GitHub Actions secrets):
  NOTION_TOKEN        - Notion internal integration token
  NOTION_DATABASE_ID  - ID of the database to query
  GMAIL_ADDRESS       - Gmail address to send FROM
  GMAIL_APP_PASSWORD  - Gmail app password (not your normal password)
  NOTIFY_EMAIL        - Email address to send TO

Configuration (edit to match your Notion database schema):
  DATE_PROPERTY      - name of the Date property
  STATUS_PROPERTY    - name of the Status property
  STATUS_DONE_VALUES - values that mean "finished" (excluded from results)
  TITLE_PROPERTY     - name of the title property
"""

import os
import smtplib
from datetime import datetime, timedelta, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from notion_client import Client

# ---- Configuration: adjust to match your Notion database ----
DATE_PROPERTY = "Due date"
STATUS_PROPERTY = "Status"
STATUS_DONE_VALUES = ["Done", "Complete", "Completed"]
TITLE_PROPERTY = "Task name"

# ---- Load secrets from environment ----
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]


def end_of_week(today: date) -> date:
    """Return the Sunday of the current week (or today if it's Sunday)."""
    days_until_sunday = (6 - today.weekday()) % 7
    return today + timedelta(days=days_until_sunday)


def get_tasks(today: date, end_date: date):
    notion = Client(auth=NOTION_TOKEN)

    # Pull everything due on or before end of week, plus overdue
    results = notion.databases.query(
        database_id=NOTION_DATABASE_ID,
        filter={
            "property": DATE_PROPERTY,
            "date": {"on_or_before": end_date.isoformat()},
        },
        sorts=[{"property": DATE_PROPERTY, "direction": "ascending"}],
    )

    tasks = []
    for page in results.get("results", []):
        props = page["properties"]

        # Skip completed tasks
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

        tasks.append({
            "title": title_text,
            "due_date": due_date,
            "url": page.get("url", ""),
            "status": status_value or "No status",
        })

    return tasks


def categorise(tasks, today: date):
    tomorrow = today + timedelta(days=1)
    overdue, due_today, due_tomorrow, due_later = [], [], [], []

    for t in tasks:
        if t["due_date"] < today:
            overdue.append(t)
        elif t["due_date"] == today:
            due_today.append(t)
        elif t["due_date"] == tomorrow:
            due_tomorrow.append(t)
        else:
            due_later.append(t)

    return overdue, due_today, due_tomorrow, due_later


# ---- HTML email builder ----

COLORS = {
    "overdue": "#C0392B",
    "today": "#E67E22",
    "tomorrow": "#2980B9",
    "later": "#27AE60",
    "bg": "#F4F5F7",
    "card": "#FFFFFF",
    "text": "#172B4D",
    "muted": "#6B778C",
    "border": "#DFE1E6",
}


def task_row(task, color):
    date_str = task["due_date"].strftime("%a %d %b")
    url = task["url"]
    title = task["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    link = (
        f'<a href="{url}" style="color:{color};text-decoration:none;font-weight:600;">{title}</a>'
        if url
        else f'<span style="font-weight:600;color:{COLORS["text"]};">{title}</span>'
    )
    return f"""
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid {COLORS['border']};">
            {link}
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid {COLORS['border']};
                     text-align:right;white-space:nowrap;color:{COLORS['muted']};
                     font-size:13px;">
            {date_str}
          </td>
        </tr>"""


def section_block(heading, badge_label, tasks, color):
    if not tasks:
        return ""
    rows = "".join(task_row(t, color) for t in tasks)
    count = len(tasks)
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="margin-bottom:24px;border-radius:6px;overflow:hidden;
                  border:1px solid {COLORS['border']};background:{COLORS['card']};">
      <tr>
        <td colspan="2" style="padding:12px 16px;background:{color};border-radius:6px 6px 0 0;">
          <span style="color:#fff;font-weight:700;font-size:14px;
                       font-family:Arial,sans-serif;letter-spacing:0.3px;">
            {heading}
          </span>
          <span style="background:rgba(255,255,255,0.25);color:#fff;
                       font-size:12px;font-weight:700;border-radius:10px;
                       padding:2px 8px;margin-left:8px;">
            {count}
          </span>
        </td>
      </tr>
      {rows}
    </table>"""


def build_html_email(overdue, due_today, due_tomorrow, due_later, today: date):
    date_display = today.strftime("%A %d %B %Y")

    body_content = (
        section_block("Overdue", "overdue", overdue, COLORS["overdue"])
        + section_block("Due Today", "today", due_today, COLORS["today"])
        + section_block("Due Tomorrow", "tomorrow", due_tomorrow, COLORS["tomorrow"])
        + section_block("Later This Week", "later", due_later, COLORS["later"])
    )

    total = len(overdue) + len(due_today) + len(due_tomorrow) + len(due_later)

    if total == 0:
        body_content = f"""
        <p style="text-align:center;color:{COLORS['muted']};font-size:15px;padding:32px 0;">
          No tasks due this week. Enjoy the clear runway.
        </p>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Task Reminder</title>
</head>
<body style="margin:0;padding:0;background:{COLORS['bg']};
             font-family:Arial,Helvetica,sans-serif;color:{COLORS['text']};">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:{COLORS['bg']};padding:32px 16px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="padding-bottom:24px;">
              <p style="margin:0;font-size:13px;color:{COLORS['muted']};
                         text-transform:uppercase;letter-spacing:0.8px;">
                Task Reminder
              </p>
              <h1 style="margin:4px 0 0;font-size:22px;font-weight:700;
                          color:{COLORS['text']};">
                {date_display}
              </h1>
            </td>
          </tr>

          <!-- Sections -->
          <tr>
            <td>
              {body_content}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding-top:16px;border-top:1px solid {COLORS['border']};">
              <p style="margin:0;font-size:12px;color:{COLORS['muted']};text-align:center;">
                Sent by your Notion Task Reminder &middot; Powered by GitHub Actions
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_subject(overdue, due_today, due_tomorrow, due_later, today: date):
    if overdue or due_today:
        total_urgent = len(overdue) + len(due_today)
        label = "task" if total_urgent == 1 else "tasks"
        parts = []
        if overdue:
            parts.append(f"{len(overdue)} overdue")
        if due_today:
            parts.append(f"{len(due_today)} due today")
        return f"Tasks due - {', '.join(parts)}"
    elif due_tomorrow or due_later:
        total = len(due_tomorrow) + len(due_later)
        label = "task" if total == 1 else "tasks"
        return f"Coming up this week - {total} {label}"
    else:
        return f"Task Reminder - all clear for {today.strftime('%a %d %b')}"


def send_email(subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [NOTIFY_EMAIL], msg.as_string())


def main():
    today = date.today()
    end_date = end_of_week(today)

    tasks = get_tasks(today, end_date)
    overdue, due_today, due_tomorrow, due_later = categorise(tasks, today)

    subject = build_subject(overdue, due_today, due_tomorrow, due_later, today)
    html_body = build_html_email(overdue, due_today, due_tomorrow, due_later, today)

    send_email(subject, html_body)
    print(f"Sent: {subject}")


if __name__ == "__main__":
    main()
