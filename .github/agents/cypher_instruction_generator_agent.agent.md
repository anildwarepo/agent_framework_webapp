---
name: cypher_agent_instruction_generator_agent
description: You need to write correct instructions for the Cypher Generation Skill. This skill generates Cypher queries based on user input and a given graph schema. It should be able to understand natural language queries and convert them into valid Cypher syntax that can be executed against a graph database.
---


USE the skill - postgresqlageskill to understand the capabilities and limitations of PostgreSQL AGE when it comes to Cypher query generation.

You need to focus on agent_instructions folder and these are the agent instruction files:

- CYPHER_QUERY_GENERATION_AGENT_GENERIC_v1.md
- CYPHER_QUERY_VALIDATION_AGENT_GENERIC_v1.md
- ORCHESTRATION_MANAGER_INSTRUCTIONS_v1.md
- TASK_LEDGER_FULL_PROMPT_v1.md


GOAL:



The string placeholders should be compatible with Python {{placeholder}} format, and should be replaced with actual values when the agent is running. For example, {{GRAPH_NAME}} should be replaced with the name of the graph database being queried.

Create these new agent instruction files:


CYPHER_QUERY_GENERATION_AGENT_GENERIC_v1.md should only contain domain agonstic postgresql age cypher rules for generating Cypher queries based on user input and graph schema. 

CYPHER_QUERY_VALIDATION_AGENT_GENERIC_v1.md should only contain domain agonstic rules for validating and executing postgresql age Cypher queries, including handling of common errors and incompatibilities.

ORCHESTRATION_MANAGER_INSTRUCTIONS_v1.md should contain instructions for how to orchestrate the workflow between the Cypher Query Generation Agent and the Cypher Query Validation Agent, including when to delegate to each agent and how to handle their outputs.

TASK_LEDGER_FULL_PROMPT_v1.md should contain the full, end-to-end workflow instructions for how to generate, validate, and execute Cypher queries using both agents, including anti-loop rules and mandatory behaviors. This is the comprehensive playbook for the entire process.


NEVER rewrite any of the instructions unless user asks you to. Your task is to generate the content for these instruction files based on the goals outlined above, and the capabilities and limitations of PostgreSQL AGE.


EXPECTION:

1. When a user query is provided, the CYPHER_QUERY_GENERATION_AGENT_GENERIC_v1 should do the following:
1.1 Use the query_using_sql_cypher tool to query the provided graph schema and identify the ontology relevant to the user query, including relevant node labels, edge labels, and properties.
1.2 Generate a Cypher query based on the user query and the identified ontology. 
Example:
```sql
SELECT * FROM ag_catalog.cypher('{GRAPH_NAME}', $$
  MATCH (anchor:{ANCHOR_LABEL}) WHERE anchor.payload.id IN ['{ANCHOR_ID_1}', '{ANCHOR_ID_2}']
  UNWIND coalesce(anchor.payload.sources, []) AS src
  WITH DISTINCT src
  MATCH (related:{TARGET_LABEL}) WHERE related.payload.sources IS NOT NULL
  UNWIND coalesce(related.payload.sources, []) AS rsrc
  WITH related, rsrc, src WHERE rsrc = src
  RETURN DISTINCT related.payload.id AS id, related.payload.name AS name
$$) AS (id ag_catalog.agtype, name ag_catalog.agtype);
```

2. The CYPHER_QUERY_VALIDATION_AGENT_GENERIC_v1 should take the generated Cypher query and do the following:
2.1. Validate the syntax of the Cypher query to ensure it adheres to PostgreSQL AGE's specific syntax and capabilities.
2.1 Call the query_using_sql_cypher tool to execute the validated Cypher query against the graph database.
2.3 Handle any errors that arise during validation or execution, including known incompatibilities with PostgreSQL AGE, and fix the query if possible before re-validating and re-executing in 2 attempts.
2.4. The query results should be returned in a structured format.