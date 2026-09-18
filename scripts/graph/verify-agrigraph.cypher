MATCH (n:Entity)
WITH count(n) AS nodes
MATCH ()-[r]->()
RETURN nodes, count(r) AS relationships,
       sum(CASE WHEN type(r) = 'HAS_SYMPTOM' THEN 1 ELSE 0 END) AS hasSymptom,
       sum(CASE WHEN type(r) = 'CAUSED_BY' THEN 1 ELSE 0 END) AS causedBy,
       sum(CASE WHEN type(r) = 'FAVORED_BY' THEN 1 ELSE 0 END) AS favoredBy,
       sum(CASE WHEN type(r) = 'CONTROLS' THEN 1 ELSE 0 END) AS controls,
       sum(CASE WHEN type(r) = 'PREVENTS' THEN 1 ELSE 0 END) AS prevents;

MATCH (n:Entity)
RETURN count(CASE WHEN 'controlMeasures' IN keys(n) THEN 1 END) AS forbiddenControlMeasures;
