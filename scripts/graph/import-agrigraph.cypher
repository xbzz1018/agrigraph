// V2 acceptance volume is project-owned; rebuild it atomically to prevent stale legacy relations.
MATCH (n:Entity) DETACH DELETE n;

CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE;
CREATE INDEX entity_label_index IF NOT EXISTS FOR (n:Entity) ON (n.label);
CREATE INDEX entity_type_index IF NOT EXISTS FOR (n:Entity) ON (n.type);

LOAD CSV WITH HEADERS FROM 'file:///agrigraph/nodes.csv' AS row
CALL {
  WITH row
  MERGE (n:Entity {id: row.id})
  SET n.label = row.label,
      n.type = row.type,
      n.aliases = [value IN split(row.aliases, '|') WHERE value <> ''],
      n.summary = row.summary,
      n.symptoms = row.symptoms,
      n.pathogen = row.pathogen,
      n.occurrenceFactors = row.occurrenceFactors,
      n.controlOptions = [value IN split(row.controlOptions, '|') WHERE value <> ''],
      n.sourceDatasetId = row.datasetId,
      n.doi = row.doi,
      n.license = row.license,
      n.sourceFile = row.sourceFile,
      n.sourceRow = toIntegerOrNull(row.sourceRow),
      n.imageObjectKey = row.imageObjectKey,
      n.thumbnailObjectKey = row.thumbnailObjectKey,
      n.imageSource = row.imageSource,
      n.sourcePage = row.sourcePage,
      n.artist = row.artist,
      n.licenseUrl = row.licenseUrl,
      n.stage = row.stage,
      n.usage = row.usage,
      n.verificationStatus = row.verificationStatus,
      n.entityName = row.entityName,
      n.sha256 = row.sha256,
      n.sourceDatasetId = CASE WHEN row.sourceDatasetId <> '' THEN row.sourceDatasetId ELSE row.datasetId END
} IN TRANSACTIONS OF 500 ROWS;

MATCH (n:Entity) WHERE n.type = 'Crop' SET n:Crop;
MATCH (n:Entity) WHERE n.type = 'Disease' SET n:Disease;
MATCH (n:Entity) WHERE n.type = 'Pest' SET n:Pest;
MATCH (n:Entity) WHERE n.type = 'Pathogen' SET n:Pathogen;
MATCH (n:Entity) WHERE n.type = 'PathogenType' SET n:PathogenType;
MATCH (n:Entity) WHERE n.type = 'EnvironmentFactor' SET n:EnvironmentFactor;
MATCH (n:Entity) WHERE n.type = 'EnvironmentThreshold' SET n:EnvironmentThreshold;
MATCH (n:Entity) WHERE n.type = 'GrowthStage' SET n:GrowthStage;
MATCH (n:Entity) WHERE n.type = 'Symptom' SET n:Symptom;
MATCH (n:Entity) WHERE n.type = 'PlantPart' SET n:PlantPart;
MATCH (n:Entity) WHERE n.type = 'ActiveIngredient' SET n:ActiveIngredient;
MATCH (n:Entity) WHERE n.type = 'BiologicalControl' SET n:BiologicalControl;
MATCH (n:Entity) WHERE n.type = 'AgriculturalPractice' SET n:AgriculturalPractice;
MATCH (n:Entity) WHERE n.type = 'OntologyConcept' SET n:OntologyConcept;
MATCH (n:Entity) WHERE n.type = 'Evidence' SET n:Evidence;
MATCH (n:Entity) WHERE n.type = 'ImageCase' SET n:ImageCase;
MATCH (n:Entity) WHERE n.type = 'Dataset' SET n:Dataset;

// 图片关系由当前核验清单重建，避免旧的猜测映射残留。
MATCH (:Entity)-[relationship:RELATED_TO]-(:Entity {type: 'ImageCase'})
WHERE relationship.type = 'HAS_IMAGE'
DELETE relationship;

LOAD CSV WITH HEADERS FROM 'file:///agrigraph/edges.csv' AS row
CALL {
  WITH row
  MATCH (source:Entity {id: row.source})
  MATCH (target:Entity {id: row.target})
  FOREACH (_ IN CASE WHEN row.type = 'HAS_SYMPTOM' THEN [1] ELSE [] END |
    MERGE (source)-[relationship:HAS_SYMPTOM {id: row.id}]->(target)
    SET relationship.label = row.label, relationship.evidence = row.evidence,
        relationship.sourceDatasetId = row.datasetId, relationship.doi = row.doi)
  FOREACH (_ IN CASE WHEN row.type = 'CAUSED_BY' THEN [1] ELSE [] END |
    MERGE (source)-[relationship:CAUSED_BY {id: row.id}]->(target)
    SET relationship.label = row.label, relationship.evidence = row.evidence,
        relationship.sourceDatasetId = row.datasetId, relationship.doi = row.doi)
  FOREACH (_ IN CASE WHEN row.type = 'FAVORED_BY' THEN [1] ELSE [] END |
    MERGE (source)-[relationship:FAVORED_BY {id: row.id}]->(target)
    SET relationship.label = row.label, relationship.evidence = row.evidence,
        relationship.sourceDatasetId = row.datasetId, relationship.doi = row.doi)
  FOREACH (_ IN CASE WHEN row.type = 'CONTROLS' THEN [1] ELSE [] END |
    MERGE (source)-[relationship:CONTROLS {id: row.id}]->(target)
    SET relationship.label = row.label, relationship.evidence = row.evidence,
        relationship.sourceDatasetId = row.datasetId, relationship.doi = row.doi)
  FOREACH (_ IN CASE WHEN row.type = 'PREVENTS' THEN [1] ELSE [] END |
    MERGE (source)-[relationship:PREVENTS {id: row.id}]->(target)
    SET relationship.label = row.label, relationship.evidence = row.evidence,
        relationship.sourceDatasetId = row.datasetId, relationship.doi = row.doi)
  FOREACH (_ IN CASE WHEN NOT row.type IN ['HAS_SYMPTOM','CAUSED_BY','FAVORED_BY','CONTROLS','PREVENTS'] THEN [1] ELSE [] END |
    MERGE (source)-[relationship:RELATED_TO {id: row.id}]->(target)
    SET relationship.type = row.type, relationship.label = row.label,
        relationship.sourceId = row.source, relationship.targetId = row.target,
        relationship.sourceDatasetId = row.datasetId, relationship.doi = row.doi,
        relationship.evidence = row.evidence)
} IN TRANSACTIONS OF 500 ROWS;
