---
name: cypher_generation_skill
description: You need to write correct instructions for the Cypher Generation Skill. This skill generates Cypher queries based on user input and a given graph schema. It should be able to understand natural language queries and convert them into valid Cypher syntax that can be executed against a graph database.
---


You need to focus on af_fastpi folder and these are the agent instruction files:

- CYPHER_QUERY_GENERATION_AGENT_GENERIC.md
- CYPHER_QUERY_VALIDATION_AGENT_GENERIC.md
- ORCHESTRATION_MANAGER_INSTRUCTIONS.md
- TASK_LEDGER_FULL_PROMPT.md


CYPHER_QUERY_GENERATION_AGENT_GENERIC.md should only contain domain agonstic rules for generating Cypher queries based on user input and graph schema. 

CYPHER_QUERY_VALIDATION_AGENT_GENERIC.md should only contain domain agonstic rules for validating and executing Cypher queries, including handling of common errors and incompatibilities.

ORCHESTRATION_MANAGER_INSTRUCTIONS.md should contain instructions for how to orchestrate the workflow between the Cypher Query Generation Agent and the Cypher Query Validation Agent, including when to delegate to each agent and how to handle their outputs.

TASK_LEDGER_FULL_PROMPT.md should contain the full, end-to-end workflow instructions for how to generate, validate, and execute Cypher queries using both agents, including anti-loop rules and mandatory behaviors. This is the comprehensive playbook for the entire process.