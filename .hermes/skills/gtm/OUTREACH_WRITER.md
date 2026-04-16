# Personalized Outreach Skill
Trigger: "write outreach for [lead]" or "draft cold email to [company]"
Agent: growth (drafts) → strategist (reviews)
Tools: Exa (lead research), himalaya (send when approved)

Workflow:
1. exa.search("[lead name] [company] recent news funding")
2. Pull ICP context from USER.md
3. Draft 3 variants: cold email, LinkedIn DM, follow-up
4. Strategist scores relevance (1-10)
5. Save: ~/outreach/ready/[lead]-[date].md
6. Send via himalaya when approved
