"""
Skill-gap analysis: compare a job description's mentioned technologies against
the candidate's actual skill set, to answer "would I pass the ATS/recruiter
skim on this one" before spending time tailoring a resume.

HAS_SKILLS is derived from data/profile.yml's `skills:` list (kept in sync
automatically) plus the fuller tool set already established in data/resume.md
and this session's tailored resumes (Terraform, Docker, Kubernetes, GCP,
Azure ADF/AKS, PostgreSQL/Oracle/SQL Server/MySQL, etc.) — profile.yml's
`skills:` list alone is a shorter curated subset used for scraper scoring,
not the full picture, so using only that would falsely flag real skills as
gaps.

WATCH_SKILLS is a curated list of common data-engineering JD terms to flag
as gaps when mentioned but not in HAS_SKILLS — deliberately not exhaustive,
just broad enough to catch the recurring ones (Microsoft Fabric, Bicep,
Data Mesh, LLM/GenAI, alternate orchestrators, etc.) seen across real JDs
this session.
"""

import re

# Extra tools/concepts confirmed as real, already-claimed skills across
# data/resume.md and this session's tailored resumes, beyond profile.yml's
# shorter `skills:` list.
_ADDITIONAL_HAS = [
    "Terraform", "Docker", "Kubernetes", "Git", "GitHub Actions", "GitLab CI",
    "CI/CD", "GCP", "Azure", "Azure Data Factory", "Azure Databricks",
    "Azure Kubernetes Service", "Azure DevOps", "PostgreSQL", "Oracle",
    "SQL Server", "MySQL", "DynamoDB", "Amazon Athena", "AWS Step Functions",
    "AWS IAM", "AWS KMS", "AWS Lake Formation", "AWS CodePipeline",
    "Salesforce API", "SSIS", "Trino", "Presto", "Hadoop", "HDFS",
    "Spark Structured Streaming", "Apache Iceberg", "Star Schema",
    "Snowflake Schema", "Dimensional Modelling", "Data Vault", "MDM",
    "Data Governance", "Data Lineage", "RBAC", "scikit-learn", "TensorFlow",
    "Amazon QuickSight", "Databricks Unity Catalog", "Databricks Workflows",
    "Delta Live Tables", "Databricks Auto Loader", "Data Contracts",
    "Root Cause Analysis", "Four-Eyes Principle Code Review",
    "Trunk-Based Development", "REST API",
    # Confirmed via LinkedIn skills export (2026-07-25) — real, endorsed
    # skills not yet reflected above.
    "PyTorch", "pandas", "NumPy", "Apache Hive", "FastAPI", "Scala",
    "Talend", "Informatica", "MLOps", "Large Language Models (LLM)",
    "Retrieval-Augmented Generation (RAG)", "Neural Networks",
    "Deep Learning", "Artificial Intelligence", "Data Mesh",
    "Amazon EC2", "Amazon CloudWatch", "AWS CloudFormation", "SharePoint",
    "JSON", "NoSQL", "Distributed Computing", "Database Architecture",
    "Information Architecture", "Business Process Management",
    "Requirements Analysis", "PL/SQL", "Bash", "Configuration Management",
    "Identity and Access Management", "Data Extraction", "Data Preparation",
    "Data Ingestion", "GitLab", "Salesforce",
]

# Common JD terms worth flagging as a gap when NOT already in HAS_SKILLS.
WATCH_SKILLS = [
    "Microsoft Fabric", "Azure Synapse", "Bicep", "ARM Templates",
    "Ansible", "Puppet", "Chef", "Pulumi",
    "Java", "Scala", "Go", "Rust", "C#", ".NET",
    "MongoDB", "Cassandra", "Redis", "Elasticsearch", "OpenSearch",
    "GraphQL", "gRPC",
    "Looker", "Qlik", "Metabase",
    "Data Mesh",
    "MLOps", "LLM", "GenAI", "Generative AI", "Agentic AI", "LangChain",
    "Vector Database", "RAG",
    "Prefect", "Dagster", "Apache NiFi", "Talend", "Informatica",
    "SAP", "Palantir Foundry", "ClickHouse", "DuckDB",
    "Amazon SageMaker", "Vertex AI", "Azure Machine Learning",
    "Pub/Sub", "Event Hubs", "RabbitMQ", "ActiveMQ",
    "Jenkins", "CircleCI", "ArgoCD",
    "Apache Beam", "Dataflow", "Apache Hive",
    "SOC 2", "ISO 27001",
]


def _aliases(skill: str) -> set:
    """A skill like 'Apache Spark' should also match a JD saying just
    'Spark'. Expands vendor-prefixed / slash-combined / acronym skills
    into all the lowercase forms a JD might use."""
    s = skill.lower().strip()
    out = {s}
    if "/" in s:
        for part in s.split("/"):
            part = part.strip()
            if part:
                out.add(part)
    for prefix in ("apache ", "aws ", "azure ", "amazon ", "google ", "microsoft "):
        if s.startswith(prefix):
            out.add(s[len(prefix):].strip())
    m = re.search(r'\(([^)]+)\)', s)
    if m:
        out.add(m.group(1).strip().lower())
        out.add(re.sub(r'\s*\([^)]*\)', '', s).strip())
    return {a for a in out if a}


def build_has_skills(profile: dict) -> dict:
    """Returns {alias: display_name} for every skill/alias the candidate has."""
    has = {}
    for skill in profile.get("skills", []) + _ADDITIONAL_HAS:
        display = skill.strip()
        for alias in _aliases(skill):
            has[alias] = display
    return has


def _build_watch_lookup() -> dict:
    return {alias: skill for skill in WATCH_SKILLS for alias in _aliases(skill)}


_WATCH_LOOKUP = _build_watch_lookup()


def analyze_job_skills(jd_text: str, profile: dict) -> dict:
    """
    Compare a job description's text against the candidate's skills.
    Returns: {"matched": [...], "gaps": [...], "fit_pct": float}
    - matched: candidate skills (display names) found mentioned in the JD
    - gaps: WATCH_SKILLS found mentioned in the JD that are NOT in HAS_SKILLS
    - fit_pct: matched / (matched + gaps) * 100 — a rough "how much of what
      this JD asks for do I already have" signal, not a full evaluation
    """
    text = (jd_text or "").lower()
    has_lookup = build_has_skills(profile)

    matched = set()
    for alias, display in has_lookup.items():
        # Word-boundary regex (below) already prevents mid-word false hits
        # (e.g. "s3" won't match inside "cars3d"), so only truly ambiguous
        # single-character aliases need skipping — "S3", "Go", "ML", "AI",
        # "BI" etc are legitimate short skill names that must still match.
        if len(alias) <= 1:
            continue
        if re.search(r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])', text):
            matched.add(display)

    gaps = set()
    for alias, display in _WATCH_LOOKUP.items():
        if display in matched or len(alias) <= 1:
            continue
        if re.search(r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])', text):
            # skip if this exact concept is already covered under a HAS alias
            if alias in has_lookup:
                continue
            gaps.add(display)

    total = len(matched) + len(gaps)
    fit_pct = round(100 * len(matched) / total, 1) if total else 0.0

    return {
        "matched": sorted(matched),
        "gaps": sorted(gaps),
        "fit_pct": fit_pct,
    }
