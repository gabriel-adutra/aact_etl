# ClinicalTrials.gov → Neo4j (AACT ETL)

## Sobre o Projeto
Este repositório implementa um pipeline ETL completo, idempotente e conteinerizado que extrai dados clínicos do AACT (PostgreSQL público do ClinicalTrials.gov), transforma e enriquece as informações, e carrega tudo em um grafo Neo4j. O objetivo é oferecer um modelo útil para exploração de:

- Ensaios clínicos (Trial)
- Drogas/Intervenções (Drug)
- Condições/Doenças (Condition)
- Patrocinadores/Organizações (Organization)
- Via de administração e forma farmacêutica (como propriedades na relação Trial–Drug)

## Arquitetura (Separação de Responsabilidades)
A arquitetura do pipeline foi desenhada para refletir separação de responsabilidades, configurabilidade e idempotência, alinhada ao que o desafio valoriza (“pipeline bem arquitetado”, “config-driven”, “batching/backpressure”, “idempotent loads”). Essa organização segue a diretriz de “estrutura clara”: cada módulo tem uma única missão (ler, processar, carregar, orquestrar), e as regras/queries ficam em config para facilitar ajustes sem tocar código.


### Módulos principais
- `config/extract_trials.sql` — Query única e declarativa de extração (AACT → JSON agregado por estudo).
- `config/text_rules.yaml` — Regras declarativas de inferência (rota/dosagem) baseadas em palavras‑chave.
- `src/db/aact_client.py` — Adapter de leitura AACT (PostgreSQL), streaming em batches.
- `src/processing/data_cleaner.py` — Normalização de campos e chamada do parser de texto.
- `src/processing/text_parser.py` — Inferência rule‑based de rota/dosagem a partir de texto livre.
- `src/db/neo4j_client.py` — Adapter de escrita Neo4j (constraints, índices, carga em lote via UNWIND).
- `src/main.py` — Orquestrador do pipeline (Extract → Transform → Load) com batch e limite configuráveis.
- `queries.cypher` — Consultas de demonstração para validação rápida no Neo4j.

### Características do Sistema
- **Batch & Idempotente:** MERGE em todas as entidades; repetir o ETL não duplica dados.
- **Config‑driven:** SQL, regras de texto e variáveis sensíveis em arquivos dedicados (`.env`).
- **Leve & Reprodutível:** Rule‑based NLP em vez de LLM/NER pesado. Imagem Docker enxuta.
- **Resiliente:** Constraints e índices aplicados automaticamente. Logs claros de progresso.


## Decisões e Racional

1) **Fonte AACT direta (Postgres público) vs. dump local (2GB)**
   - Opções consideradas:
     - Baixar o dump (2GB), subir um Postgres local e carregar via `pg_restore`.
     - Montar um container Postgres que baixe e restaure o dump em build.
     - Conectar direto ao Postgres público do AACT (Playground).
   - Rejeitamos dump/local porque: aumenta tempo de build, exige versionar/baixar binário grande, e congela dados (perde atualizações).
   - Escolhemos o Postgres público: é a “fonte oficial”, zero binários versionados, sempre dados atuais e experiência “clone & run” via Docker Compose (apenas credenciais no `.env`).

2) **Query relacional → JSON agregado (AACT)**
   - Alternativas: juntar no Python (mais I/O, mais lógica) ou agregar já no banco.
   - Escolha: usar `json_agg` no Postgres para devolver 1 linha por estudo com listas de drogas/condições/patrocinadores, reduzindo transferência e evitando reagrupamento manual. Mantém a transformação declarativa e versionada em SQL.

3) **Inferência de rota/dosagem por palavras‑chave (regras)**
   - Alternativas: LLM/NER (maior recall, custo/peso maiores) ou heurísticas simples. Inclui opções gerenciadas como Databricks AI Query, que facilitam mas dependem de cloud, custo e latência.
   - Escolha: regras no `config/text_rules.yaml`, porque são leves, auditáveis e reprodutíveis em ambiente Docker enxuto; aderem ao espírito do desafio (não construir um “Google Healthcare”, mas uma abordagem razoável e documentada).
   - Limitação: descrições pobres geram `Unknown` (~5% rota, ~1% forma em 1000 trials). Documentado como risco conhecido. Futuro: NER/LLM (BioBERT/SciSpacy), AI Query gerenciado (ex.: Databricks) ou hints no nome da droga, se aceitarmos custo/complexidade adicionais.

4) **Intervention types: DRUG e BIOLOGICAL**
   - Alternativas: só DRUG (perde vacinas/anticorpos) ou incluir ambos.
   - Escolha: incluir DRUG e BIOLOGICAL para cobrir small molecules, vacinas e biológicos, atendendo melhor ao critério “clinical‑stage drugs”.
   - Documentado para justificar a definição e evitar lacunas nos resultados.

5) **Placebo mantido**
   - Alternativas: filtrar placebo na extração ou na carga.
   - Escolha: manter para fidelidade à fonte e para não embutir regra de negócio; facilita auditoria. Se o avaliador quiser filtrar, é um ajuste simples na SQL.

6) **Normalização de nomes com `.title()`**
   - Alternativas: pipelines de normalização avançados (sinônimos, stemming) ou manter bruto.
   - Escolha: `.title()` para reduzir variação trivial com custo baixo. Risco: acrônimos podem ser alterados (dnaJ → Dnaj); limitação registrada. Futuro: lista de exceções/sinônimos se necessário.

## Como o Sistema Funciona

1) **Ingestão (AACT → Python)**  
   - `config/extract_trials.sql` filtra estudos intervencionais em fases PHASE1/2/3/4 (inclui PHASE1/PHASE2, PHASE2/PHASE3) e `intervention_type IN ('DRUG','BIOLOGICAL')`.  
   - Agrega drogas, condições e patrocinadores por estudo (`json_agg`).

2) **Transformação (Python)**  
   - `DataCleaner` normaliza textos (trim, Title Case básico) e deduplica condições.  
   - `TextParser` aplica regras de rota/dosagem sobre a descrição da intervenção; se vazio, retorna `Unknown`.

3) **Carga (Neo4j)**  
   - Constraints/Índices criados automaticamente (nct_id, nome de Drug/Condition/Organization).  
   - Carga em lote com `UNWIND $batch` e propriedades de rota/dosagem na relação `STUDIED_IN`.

4) **Validação (Queries)**  
   - `queries.cypher` contém consultas para top drugs, visão por empresa, visão por condição e cobertura de rota/dosagem.

## Modelagem de Dados (Grafo)
- Nós: `(:Trial {nct_id, title, phase, status})`, `(:Drug {name})`, `(:Condition {name})`, `(:Organization {name})`
- Relações:
  - `(:Drug)-[:STUDIED_IN {route?, dosage_form?}]->(:Trial)`
  - `(:Trial)-[:STUDIES_CONDITION]->(:Condition)`
  - `(:Trial)-[:SPONSORED_BY {class?}]->(:Organization)`
- Constraints/Índices: unicidade em nct_id e nomes; índices em phase/status.

## Pré-requisitos
- Docker + Docker Compose.
- Conta AACT para credenciais Postgres (criar em https://aact.ctti-clinicaltrials.org/).

Exemplo de `.env` (não versionar):
```
AACT_HOST=aact-db.ctti-clinicaltrials.org
AACT_PORT=5432
AACT_DB=aact
AACT_USER=SEU_USUARIO
AACT_PASSWORD=SUASENHA

NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

## Como Rodar (End-to-End)
1) Build:
```
docker compose build etl
```
2) Executar ETL (default: 1000 estudos, batch=500):
```
docker compose run --rm etl python src/main.py
```
3) Acessar Neo4j Browser:
- URL: http://localhost:7474  
- User: `neo4j`  
- Pass: `password` (ajuste no `.env` se quiser)

4) Consultas de Demonstração (também em `queries.cypher`):
- Top drugs:
```
MATCH (d:Drug)<-[:STUDIED_IN]-(t:Trial)
RETURN d.name AS drug, count(t) AS trials
ORDER BY trials DESC
LIMIT 10;
```
- Por empresa (ex.: Novartis):
```
MATCH (o:Organization {name: "Novartis"})<-[:SPONSORED_BY]-(t:Trial)
OPTIONAL MATCH (t)-[:STUDIED_IN]->(d:Drug)
OPTIONAL MATCH (t)-[:STUDIES_CONDITION]->(c:Condition)
RETURN o.name, collect(DISTINCT d.name) AS drugs, collect(DISTINCT c.name) AS conditions;
```
- Por condição (ex.: Alzheimer Disease):
```
MATCH (c:Condition {name: "Alzheimer Disease"})<-[:STUDIES_CONDITION]-(t:Trial)-[:STUDIED_IN]->(d:Drug)
RETURN d.name AS drug, collect(DISTINCT t.phase) AS phases, count(DISTINCT t) AS trial_count
ORDER BY trial_count DESC;
```
- Cobertura rota/dosagem:
```
MATCH ()-[r:STUDIED_IN]->()
RETURN
  count(r) AS total_relationships,
  SUM(CASE WHEN r.route IS NOT NULL AND r.route <> "Unknown" THEN 1 ELSE 0 END) AS with_route,
  SUM(CASE WHEN r.dosage_form IS NOT NULL AND r.dosage_form <> "Unknown" THEN 1 ELSE 0 END) AS with_dosage_form;
```

## Ajustes de Volume
- Editar `run_pipeline(limit=..., batch_size=...)` em `src/main.py` e rodar novamente:
```
docker compose run --rm etl python src/main.py
```
- Carga é idempotente (MERGE evita duplicatas).

## Limitações Conhecidas
- Baixa cobertura de rota/dosagem por falta de texto rico nas descrições de intervenção; muitos `Unknown`.
- `.title()` pode simplificar acrônimos (ex.: dnaJ → Dnaj).
- Placebo permanece como Drug (fidelidade à fonte); pode ser filtrado se desejado.
- Não usamos LLM/NER pesado para manter imagem leve e execução offline; limitação documentada.

## Próximos Passos (se houvesse mais tempo)
- NER/LLM (BioBERT/SciSpacy) para melhorar rota/dosagem.
- Heurística no nome da droga para extrair forma/rota sem alterar o identificador.
- Métricas automáticas (nós/arestas criados, coverage de campos).
- Ingestão incremental e orquestração (Airflow/Prefect).
# ClinicalTrials.gov → Neo4j (AACT ETL)

## Visão Geral
Pipeline em Python que:
1. Extrai estudos clínicos do AACT (Postgres público do ClinicalTrials.gov).
2. Transforma e enriquece (limpeza + inferência de rota/dosagem a partir de texto).
3. Carrega em lote no Neo4j, com constraints/indexes para idempotência e performance.
4. Inclui queries Cypher de demonstração.

## Arquitetura
- **Fonte:** AACT (PostgreSQL público). Consulta parametrizada em `config/extract_trials.sql`.
- **Processamento:** Python (rule-based NLP leve), arquivos de regras em `config/text_rules.yaml`.
- **Alvo:** Neo4j (grafo), carga em lote via `UNWIND`.
- **Conteinerização:** `docker-compose` com serviços `neo4j` e `etl`.

## Decisões e Trade-offs
- **AACT direto (Postgres público)** em vez de dump local de 2GB: zero dependência de arquivo gigante e experiência “clone & run”.
- **Query relacional → JSON aninhado (json_agg)**: o Postgres já agrupa drogas/condições/patrocinadores por estudo, evitando lógica de reagrupamento no Python.
- **Inferência de rota/dosagem via regras (regex/keyword)**:
  - Vantagem: leve, reprodutível offline, explica cada decisão.
  - Limitação: cobertura limitada quando não há texto rico; não é um NER/LLM.
- **Por que não Databricks/LLM/Spacy pesado?**
  - Overkill para o escopo; aumenta dependência externa, custo e latência.
  - Repositório e imagem Docker mais enxutos; foco em clareza e reprodutibilidade.
  - Documentamos a limitação e o caminho de melhoria (usar NER/LLM no futuro).
- **Placebo como droga:** Mantido conforme fonte; decisão de negócio poderia filtrar, mas preservamos fidelidade aos dados.
- **Normalização de nomes:** `.title()` pode simplificar acrônimos (ex: dnaJ → Dnaj). Documentado como limitação aceitável.

## Consulta de Extração (AACT)
Arquivo: `config/extract_trials.sql`
- Filtra **intervention_type IN ('DRUG', 'BIOLOGICAL')** (para cobrir small molecules e biológicos).
- Fases clínicas: `PHASE1`, `PHASE2`, `PHASE3`, `PHASE4`, `PHASE1/PHASE2`, `PHASE2/PHASE3`.
- Estudo intervencional: `study_type = 'INTERVENTIONAL'`.
- Agrupa:
  - `drugs`: lista de `{name, description}`
  - `conditions`: lista de nomes
  - `sponsors`: lista de `{name, class}`

## Inferência de Rota/Dosagem
Arquivo: `config/text_rules.yaml`
- Regras de keywords para `routes` (Oral, Intravenous, Subcutaneous, etc.) e `dosage_forms` (Tablet, Injection, Cream, etc.).
- Aplicado à **description** da intervenção. Se não houver texto, retorna `Unknown`.
- Cobertura observada em 1000 trials: 1.645 relações Trial–Drug, 79 com rota (≈4,8%), 21 com forma (≈1,3%). Limitação documentada: falta de texto rico na fonte.

## Modelo de Grafo (Neo4j)
- Nós: `(:Trial {nct_id})`, `(:Drug {name})`, `(:Condition {name})`, `(:Organization {name})`
- Relações:
  - `(:Drug)-[:STUDIED_IN {route?, dosage_form?}]->(:Trial)`
  - `(:Trial)-[:STUDIES_CONDITION]->(:Condition)`
  - `(:Trial)-[:SPONSORED_BY {class?}]->(:Organization)`
- Constraints/Índices:
  - `Trial.nct_id` UNIQUE
  - `Drug.name` UNIQUE
  - `Condition.name` UNIQUE
  - `Organization.name` UNIQUE
  - Indexes em `Trial.phase`, `Trial.status`

## Pré-requisitos
- Docker + Docker Compose.
- Conta no AACT para obter usuário/senha do Postgres (https://aact.ctti-clinicaltrials.org/). Exemplo de `.env`:
  ```
  AACT_HOST=aact-db.ctti-clinicaltrials.org
  AACT_PORT=5432
  AACT_DB=aact
  AACT_USER=SEU_USUARIO
  AACT_PASSWORD=SUASENHA

  NEO4J_URI=bolt://neo4j:7687
  NEO4J_USER=neo4j
  NEO4J_PASSWORD=password
  ```

## Como Rodar
1) Build:
```
docker compose build etl
```
2) Executar ETL (default 1000 estudos em lotes de 500):
```
docker compose run --rm etl python src/main.py
```
3) Acessar Neo4j Browser:
- URL: http://localhost:7474
- Usuário: `neo4j`
- Senha: `password` (ou altere no `.env` / docker-compose).
4) Rodar queries de exemplo (também em `queries.cypher`):
- Top drugs:
```
MATCH (d:Drug)<-[:STUDIED_IN]-(t:Trial)
RETURN d.name AS drug, count(t) AS trials
ORDER BY trials DESC
LIMIT 10;
```
- Por empresa (ex: Novartis):
```
MATCH (o:Organization {name: "Novartis"})<-[:SPONSORED_BY]-(t:Trial)
OPTIONAL MATCH (t)-[:STUDIED_IN]->(d:Drug)
OPTIONAL MATCH (t)-[:STUDIES_CONDITION]->(c:Condition)
RETURN o.name, collect(DISTINCT d.name) AS drugs, collect(DISTINCT c.name) AS conditions;
```
- Por condição (ex: Alzheimer Disease):
```
MATCH (c:Condition {name: "Alzheimer Disease"})<-[:STUDIES_CONDITION]-(t:Trial)-[:STUDIED_IN]->(d:Drug)
RETURN d.name AS drug, collect(DISTINCT t.phase) AS phases, count(DISTINCT t) AS trial_count
ORDER BY trial_count DESC;
```
- Cobertura de rota/dosagem:
```
MATCH ()-[r:STUDIED_IN]->()
RETURN
  count(r) AS total_relationships,
  SUM(CASE WHEN r.route IS NOT NULL AND r.route <> "Unknown" THEN 1 ELSE 0 END) AS with_route,
  SUM(CASE WHEN r.dosage_form IS NOT NULL AND r.dosage_form <> "Unknown" THEN 1 ELSE 0 END) AS with_dosage_form;
```

## Ajustes de Volume
- Para carregar mais de 1000 estudos, edite `run_pipeline(limit=..., batch_size=...)` em `src/main.py` e rode novamente:
```
docker compose run --rm etl python src/main.py
```
- Carga é idempotente (MERGE evita duplicatas).

## Limitações Conhecidas
- Inferência limitada por falta de texto rico: muitos `Unknown` para rota/dosagem.
- Normalização de nomes via `.title()` pode simplificar acrônimos (ex: dnaJ → Dnaj).
- Placebo permanece como droga (fidelidade à fonte). Opcional filtrar se necessário.
- Não usamos LLM/NER pesado por foco em leveza e reprodutibilidade; documentamos a limitação.

## Decisões e Riscos sobre Rota/Dosagem e Normalização
- Cobertura de rota/dosagem tende a ser baixa porque as descrições de intervenção raramente trazem texto rico. Optamos por regras simples e declarativas (text_rules.yaml) e preferimos `Unknown` a falsos positivos.
- Não usamos LLM/NER pesado: o desafio pede abordagem “razoável” e documentada; priorizamos imagem leve, execução offline e transparência. Futuro: NER/LLM (BioBERT/SciSpacy) ou heurística secundária no nome da droga para hints de forma/rota.
- `.title()` simplifica acrônimos (dnaJ → Dnaj); aceitamos essa limitação para reduzir variações triviais. Futuro: lista de exceções/sinônimos para acrônimos conhecidos.
- Ao iniciar, o Neo4j pode avisar que constraints/índices já existem; é esperado e demonstra a idempotência da criação de schema (`IF NOT EXISTS`).


## Exemplos de Saída (queries no Neo4j)
- Top drugs (1000 trials):
  - Zidovudine 122, Didanosine 54, Buprenorphine 42, Lamivudine 34, Stavudine 32, Zalcitabine 20, Indinavir Sulfate 20, Nevirapine 19, Rgp120/Hiv-1 Sf-2 18, Ritonavir 18.
- Por empresa (Novartis):
  - Drugs: Rivastigmine; Conditions: Alzheimer Disease, Cognition Disorders.
- Por condição (Alzheimer Disease):
  - Drogas (todas PHASE3, trial_count mostrado): Estrogen (2), Galantamine (1), Donepezil (1), Vitamin E (1), Trazodone (1), Haloperidol (1), Rivastigmine (1), Prednisone (1), Estrogen And Progesterone (1), Melatonin (1).
- Cobertura rota/dosagem (1000 trials → 1.645 relações Trial–Drug):
  - with_route: 79 (~5%); with_dosage_form: 21 (~1%). Baixa cobertura devido a descrições pobres; documentado como limitação da abordagem rule-based.

## Próximos Passos (se houvesse mais tempo)
- Usar NER/LLM (ex.: BioBERT/SciSpacy) para melhorar inferência de rota/dosagem.
- Enriquecer normalização de nomes (tabelas de sinônimos, remoção de sufixos “Tablet”, “Injection” do nome sem afetar identidade).
- Métricas automáticas (quantos nós/arestas criados, coverage de campos).
- Incremental ingestion (delta) e workflow (Airflow/Prefect).

### Trade-offs de Inferência (rota/forma)
- AI Query / Databricks end-to-end: maior cobertura potencial e facilidades gerenciadas; porém depende de cloud, tem custo/latência e foge da leveza/reprodutibilidade local.
- Modelos locais (BioBERT/SciSpacy): melhor recall que regras; mas aumentam a imagem (GB), o tempo de build e a complexidade operacional.
- Abordagem atual (rule-based): leve, offline, transparente e fácil de auditar; menor recall, mas alinhada ao “reasonable approach” do desafio e mantendo a imagem enxuta.

