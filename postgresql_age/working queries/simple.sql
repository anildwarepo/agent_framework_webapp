SET search_path=ag_catalog,"$user",public;

// simple query for a given customer name
SELECT * FROM cypher('customer_graph', $$
MATCH (n:Customer)
WHERE n.payload.name = 'Customer 080'
RETURN id(n) AS id, labels(n) AS label, n.payload AS properties,
	'node' AS kind, NULL AS src, NULL AS dst

$$) AS (id ag_catalog.agtype,
                label ag_catalog.agtype,
                properties ag_catalog.agtype,
                kind ag_catalog.agtype,
                src ag_catalog.agtype,
                dst ag_catalog.agtype);



SELECT * FROM cypher('customer_graph', $$
MATCH (v:Customer)
RETURN v
LIMIT 3
$$) as (v agtype);


// simple query to see connected nodes

SELECT * FROM cypher('customer_graph', $$
MATCH (v:Customer)-[:ADOPTED_PRODUCT]-(m)
RETURN m
LIMIT 3
$$) as (m agtype);


// what are the top 3 products used by 'Customer 080'
SELECT *
FROM ag_catalog.cypher('customer_graph', $$

  MATCH (c:Customer)
  WHERE c.payload.name = 'Customer 080'
  OPTIONAL MATCH (c)-[:ADOPTED_PRODUCT]->(p:Product)

  WITH c, p
  ORDER BY coalesce(p.payload.name, '') ASC

  WITH c,
       collect(
         CASE WHEN p IS NOT NULL
              THEN p.payload.name
              ELSE NULL
         END
       ) AS raw_names

  WITH c, [x IN raw_names WHERE x IS NOT NULL][0..3] AS top_products

  RETURN coalesce(c.payload.name, '') AS customer_name,
         top_products

$$) AS (
  customer_name ag_catalog.agtype,
  top_products  ag_catalog.agtype
);



// what are the  3 products used by the same customers

SELECT *
FROM ag_catalog.cypher('customer_graph', $$

  MATCH (c:Customer)
  WHERE c.payload.name = 'Customer 080'

  OPTIONAL MATCH (c)-[:ADOPTED_PRODUCT]->(p_c:Product)
  WITH c, collect(DISTINCT p_c) AS adopted_products

  // pick up to 3 seed products
  WITH c, [x IN adopted_products WHERE x IS NOT NULL][0..3] AS seed_products
  UNWIND seed_products AS seed

  OPTIONAL MATCH (cust:Customer)-[:ADOPTED_PRODUCT]->(seed)
  WITH seed_products, collect(DISTINCT cust) AS cohort

  UNWIND cohort AS cust
  OPTIONAL MATCH (cust)-[:ADOPTED_PRODUCT]->(p2:Product)
  WHERE p2 IS NOT NULL AND NOT p2 IN seed_products

  // aggregate
  WITH p2, count(DISTINCT cust) AS adopter_count

  // extra WITH to avoid the bug
  WITH p2, adopter_count
  ORDER BY adopter_count DESC, p2.payload.name ASC
  LIMIT 3

  RETURN p2.payload.name AS product_name, adopter_count

$$) AS (
  product_name ag_catalog.agtype,
  adopter_count ag_catalog.agtype
);

