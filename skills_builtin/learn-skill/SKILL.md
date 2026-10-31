---
name: learn-skill
description: Turn a procedure you just completed (or the user describes) into a reusable skill.
---
1. Write the steps as a short numbered list that another run of you could follow: which tools, in which order, and what to check at the end.
2. Pick a short lowercase name with dashes and a one-line description that says WHEN to use it.
3. Call create_skill with name, description and instructions. If a PowerShell script would make it more reliable, say so; the user can drop a .ps1 into the skill folder and you can run it with run_skill_script.
4. Tell the user the skill name so they can ask for it next time.
