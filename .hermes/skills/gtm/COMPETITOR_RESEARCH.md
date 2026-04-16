# Competitor Research Skill
Trigger: "research [competitor]" or "competitive analysis"
Agent: strategist
Tools: Exa (EXA_API_KEY), blogwatcher-cli
Output: ~/reports/competitors/[name]-[date].md

Workflow:
1. exa.search("[competitor] pricing features 2026")
2. exa.get_contents([pricing_url], text={"max_characters": 3000})
3. Extract: pricing tiers, ICP, differentiators, recent updates
4. Append 2-line delta to MEMORY.md under ## Competitive Intel
5. Append row to ~/reports/competitors/INDEX.md
