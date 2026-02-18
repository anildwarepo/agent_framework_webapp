SHOW server_version;

-- run on database 'postgres'
CREATE EXTENSION IF NOT EXISTS AGE CASCADE;


SELECT * FROM pg_extension WHERE extname = 'age';


SET search_path=ag_catalog,"$user",public;


SELECT * FROM ag_catalog.ag_graph;

SHOW shared_preload_libraries;    


ALTER DATABASE postgres SET search_path = ag_catalog, "$user", public;




-- CYPHER queries

SET search_path=ag_catalog,"$user",public;

SELECT * FROM cypher('age_smoke', $$
MATCH (n)
RETURN id(n) AS id, labels(n) AS label, n.payload AS properties,
	'node' AS kind, NULL AS src, NULL AS dst
UNION ALL
// edges
MATCH (s)-[e]->(t)
RETURN id(e) AS id, [type(e)] AS label, properties(e) AS properties,
	'edge' AS kind, id(s) AS src, id(t) AS dst
$$) AS (id ag_catalog.agtype,
                label ag_catalog.agtype,
                properties ag_catalog.agtype,
                kind ag_catalog.agtype,
                src ag_catalog.agtype,
                dst ag_catalog.agtype);


