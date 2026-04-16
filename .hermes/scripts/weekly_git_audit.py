import datetime
today = datetime.date.today().isoformat()

print(f"""
WEEKLY GIT AUDIT — {today}
Agent: devops

Audit all code on this VPS that is not backed up to GitHub.

Run these commands and report findings:

1. Find all git repos on the VPS:
   find /root -name ".git" -type d 2>/dev/null | grep -v ".hermes"

2. For each repo found, check:
   - git status (any uncommitted changes?)
   - git log origin/main..HEAD (any unpushed commits?)
   - Remote URL (is it linked to GitHub?)

3. Find directories that look like code projects but have NO git repo:
   find /root -maxdepth 2 -name "*.py" -o -name "package.json" -o -name "requirements.txt" 2>/dev/null | grep -v ".hermes" | grep -v "venv" | xargs -I{{}} dirname {{}} | sort -u

4. Report:
   - List of repos with unpushed changes and what they contain
   - List of code directories with NO git backup at all
   - Recommended action for each

Save report to: /root/reports/git-audit-{today}.md
Send a Telegram summary with:
- Total repos found
- How many have unpushed changes
- How many have no git at all
- Top 3 most urgent to back up
""")
