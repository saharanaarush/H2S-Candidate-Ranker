"""Encoded target profile for the Redrob 'Senior AI Engineer — Founding Team' JD.

Everything the ranker knows about the role lives here as plain data: keyword
taxonomies, company lists, and the component weights. Keeping it declarative
makes the scoring logic in scoring.py easy to read and easy to defend in a
review/interview (which the spec's Stage 5 explicitly checks).

Design intent (from job_description.docx, "how to read between the lines"):
  * The role is applied ML/IR at a PRODUCT company, tilted toward shipping.
  * Reward retrieval / ranking / recommendation / search / embeddings EVIDENCE
    in career history — not just AI keywords in the skills list.
  * Punish keyword-stuffers: non-technical titles with a glossy AI skill list.
  * Punish services-only careers (TCS/Infosys/Wipro/...), pure-research-only,
    and primary CV/speech/robotics backgrounds without NLP/IR.
  * Down-weight behaviourally unavailable candidates (inactive, low response).
  * Honeypots (impossible profiles) must never reach the top 100.
"""

# --------------------------------------------------------------------------- #
# Component weights (must sum to 1.0). These feed the skills/fit composite,
# which is then multiplied by the behavioural modifier and honeypot gate.
# --------------------------------------------------------------------------- #
WEIGHTS = {
    "title_career": 0.26,   # is this actually an ML/eng career? (anti keyword-stuffer)
    "domain": 0.20,         # NLP / IR / ranking / retrieval / recsys relevance
    "skills": 0.18,         # trust-weighted required-skill coverage
    "experience": 0.12,     # 5-9 yrs sweet spot
    "production": 0.12,     # product-company vs services-only
    "location": 0.08,       # Pune/Noida/Indian Tier-1, or relocatable
    "education": 0.04,      # minor tie-breaker
}

# --------------------------------------------------------------------------- #
# Title taxonomy. Lowercase substring matching against current/recent titles.
# Order matters: the first bucket that matches wins (most specific first).
# --------------------------------------------------------------------------- #
TITLE_BUCKETS = [
    ("ai_ml", 1.00, [
        "machine learning", "ml engineer", "ai engineer", "applied scientist",
        "applied ml", "data scientist", "nlp engineer", "research engineer",
        "research scientist", "ml scientist", "ai scientist", "deep learning",
        "ml/ai", "ai/ml", "recommendation", "search engineer", "relevance",
        "ranking",
    ]),
    ("data_eng", 0.78, [
        "data engineer", "analytics engineer", "ml platform", "data platform",
        "mlops",
    ]),
    ("swe", 0.62, [
        "software engineer", "backend engineer", "back-end", "full stack",
        "fullstack", "platform engineer", "software developer", "sde",
        "staff engineer", "principal engineer", "founding engineer",
    ]),
    ("other_tech", 0.40, [
        "developer", "devops", "cloud engineer", "qa engineer", "sre",
        "mobile", "frontend", "front-end", "android", "ios", "data analyst",
        "database", "systems engineer",
    ]),
    # Everything else is treated as non-technical (score handled in scoring.py).
]

# Clearly non-technical titles — used to flag keyword-stuffer traps explicitly.
NON_TECH_TITLES = [
    "marketing", "hr ", "human resresource", "human resource", "sales",
    "operations manager", "customer support", "content writer", "accountant",
    "business analyst", "mechanical engineer", "civil engineer",
    "chemical engineer", "graphic designer", "project manager", "recruiter",
    "talent", "finance", "consultant", "administrator", "coordinator",
]

# --------------------------------------------------------------------------- #
# Domain keyword sets. Matched against the candidate's free-text "evidence"
# corpus (headline + summary + career descriptions), where REAL experience
# shows up — not just the skills array.
# --------------------------------------------------------------------------- #
IR_RANKING_TERMS = [
    "recommendation", "recommender", "ranking", "rank ", "learning to rank",
    "learning-to-rank", "retrieval", "search", "semantic search",
    "information retrieval", "personalization", "personalisation", "relevance",
    "vector search", "nearest neighbor", "nearest neighbour", "ann ",
    "matching", "embedding", "embeddings", "rag", "bm25", "elasticsearch",
    "opensearch", "faiss", "two-tower", "candidate generation",
]
NLP_TERMS = [
    "nlp", "natural language", "transformer", "bert", "llm", "language model",
    "text classification", "named entity", "sentence-transformers",
    "sentence transformers", "tokeniz", "question answering", "summarization",
]
# Primary domains the JD explicitly says it does NOT want (without NLP/IR).
OFFDOMAIN_TERMS = [
    "image classification", "object detection", "computer vision", "opencv",
    "image segmentation", "speech recognition", "text-to-speech", "tts",
    "asr", "robotics", "slam", "autonomous", "lidar", "gan", "gans",
    "diffusion", "pose estimation", "video analytics",
]

# --------------------------------------------------------------------------- #
# Required / nice-to-have skill families. Each maps to match terms. Required
# families are weighted higher in the skills component.
# --------------------------------------------------------------------------- #
SKILL_FAMILIES = {
    # family: (is_required, weight, [terms])
    "embeddings_retrieval": (True, 1.0, [
        "embedding", "embeddings", "sentence-transformers", "sentence transformers",
        "bge", "e5", "retrieval", "semantic search", "rag", "bm25", "hybrid search",
    ]),
    "vector_db": (True, 1.0, [
        "pinecone", "weaviate", "qdrant", "milvus", "faiss", "opensearch",
        "elasticsearch", "vector database", "vector db", "vector search",
    ]),
    "python": (True, 0.7, ["python"]),
    "evaluation": (True, 0.9, [
        "ndcg", "mrr", "map@", "mean average precision", "a/b test", "ab test",
        "ab testing", "offline evaluation", "ranking metrics", "recall@",
        "precision@",
    ]),
    "ranking_models": (False, 0.6, [
        "learning to rank", "learning-to-rank", "xgboost", "lightgbm",
        "ranknet", "lambdamart", "gradient boost",
    ]),
    "llm_finetune": (False, 0.5, [
        "fine-tuning", "fine tuning", "finetune", "lora", "qlora", "peft",
        "instruction tuning",
    ]),
    "distributed": (False, 0.4, [
        "spark", "kafka", "airflow", "distributed", "kubernetes", "ray",
    ]),
}

# --------------------------------------------------------------------------- #
# Services / consulting firms. A career spent ENTIRELY here is a JD disqualifier
# ("People who have only worked at consulting firms ... in their entire career").
# --------------------------------------------------------------------------- #
SERVICES_FIRMS = {
    "tcs", "tata consultancy", "infosys", "wipro", "accenture", "cognizant",
    "capgemini", "tech mahindra", "hcl", "hcltech", "dxc", "mindtree",
    "ltimindtree", "mphasis", "hexaware", "birlasoft", "igate", "syntel",
    "larsen", "l&t infotech", "lti", "deloitte", "cognizant technology",
    "ibm services", "atos", "ntt data",
}

# Indian Tier-1 cities the JD names or implies (Pune/Noida strongest).
TIER1_CITIES_TOP = ["pune", "noida"]
TIER1_CITIES = [
    "pune", "noida", "hyderabad", "mumbai", "delhi", "new delhi", "gurgaon",
    "gurugram", "bengaluru", "bangalore", "chennai", "ncr", "giser",
]

# Reference 'today' for recency math. Matches the dataset's current window.
TODAY_ISO = "2026-06-18"
