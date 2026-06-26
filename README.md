# Notion Task Due Date Reminder

Emails you a daily summary of Notion tasks that are overdue, due today, or due tomorrow.

## 1. Create a Notion integration

1. Go to https://www.notion.so/profile/integrations
2. Click **New integration**, give it a name (e.g. "Task Reminder"), select your workspace.
3. Copy the **Internal Integration Secret** - this is your `NOTION_TOKEN`.

## 2. Share your database with the integration

1. Open your tasks database in Notion.
2. Click the `...` menu (top right) → **Connections** → search for your integration name → connect it.
3. Without this step, the integration cannot see your database.

## 3. Get your database ID

1. Open the database as a full page in your browser.
2. The URL looks like: `https://www.notion.so/yourworkspace/DATABASE_ID?v=...`
3. `DATABASE_ID` is a 32-character string (with or without hyphens) - copy it. This is `NOTION_DATABASE_ID`.

## 4. Check your database's property names

Open `notion_reminder.py` and check these match your actual database columns:

```python
DATE_PROPERTY = "Due Date"      # your Date property name
STATUS_PROPERTY = "Status"      # your Status/Checkbox property name
STATUS_DONE_VALUES = ["Done", "Complete", "Completed"]  # values that mean "finished"
TITLE_PROPERTY = "Name"         # your title column name (usually "Name")
```

Edit these to match exactly (case-sensitive) before pushing.

## 5. Create a Gmail app password

You can't use your normal Gmail password for SMTP. You need an app password:

1. Turn on 2-Step Verification on your Google account if not already on: https://myaccount.google.com/security
2. Go to https://myaccount.google.com/apppasswords
3. Create a new app password (name it "Notion Reminder"), copy the 16-character password.

## 6. Push this to a GitHub repo

```bash
cd notion-reminder
git init
git add .
git commit -m "Notion task reminder"
git remote add origin https://github.com/YOUR_USERNAME/notion-reminder.git
git push -u origin main
```

Make the repo **private** since the workflow file references secrets (the secrets themselves are safe either way, but no reason to make it public).

## 7. Add GitHub repo secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**. Add each of:

| Secret name | Value |
|---|---|
| `NOTION_TOKEN` | Your integration secret from step 1 |
| `NOTION_DATABASE_ID` | Your database ID from step 3 |
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | The 16-character app password from step 5 |
| `NOTIFY_EMAIL` | Where you want the reminder sent (can be the same Gmail address) |

## 8. Test it manually

Go to the **Actions** tab in your repo → select "Notion Task Reminder" → **Run workflow** (this works because of the `workflow_dispatch` trigger in the YAML). Check your email a few seconds later.

## 9. Adjust the schedule

The cron is set to `0 7 * * *`, which is 07:00 UTC every day. GitHub Actions cron always runs in UTC, so adjust for your timezone and for BST/GMT shifts if you want a consistent local time. Edit the line in `.github/workflows/reminder.yml`:

```yaml
- cron: "0 7 * * *"
```

Note: GitHub Actions scheduled workflows can be delayed by a few minutes during high-load periods - this is normal and not something you can control.

## Customising

- `LOOKAHEAD_DAYS` in `notion_reminder.py` controls how far ahead to look (1 = today + tomorrow).
- `INCLUDE_OVERDUE` toggles whether overdue tasks are included.
- The email is plain text; you can switch `MIMEText(body)` to `MIMEText(body, "html")` and build an HTML body if you want it to look nicer.
