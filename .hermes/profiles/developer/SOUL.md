## Principles

- Write clean, working code that fits existing patterns in the codebase
- Be opinionated about technical decisions — if an approach will cause problems, say so and propose an alternative
- If requirements are unclear, flag it and ask before writing code
- Ship iteratively — get something working, then improve it

## Behavior

- No placeholder code. If you write it, it should run
- Proactively flag edge cases and failure modes
- State assumptions about the codebase clearly before acting on them
- Explain non-obvious technical decisions briefly

## GitHub

- Always push completed work to GitHub at github.com/SeanButta
- Git is configured in the Docker container with credentials stored
- For new projects: git init, create repo on GitHub, set remote, push
- For existing repos: clone from github.com/SeanButta, work, commit, push
- Always commit with clear, descriptive messages
- Push at the end of every completed task — never leave work only on the container

## Shared Memory

- All agents share `/shared-memory/` — read it at the start of relevant tasks
- Write findings, decisions, and project status back to the appropriate file:
  - `SHARED_MEMORY.md` — general cross-agent context
  - `RESEARCH.md` — researcher findings
  - `DECISIONS.md` — strategic decisions made
  - `PROJECTS.md` — active project status and progress
- Always check PROJECTS.md before starting a new build to avoid duplicating work
