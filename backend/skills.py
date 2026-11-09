# backend/skills.py
# Skill vocabulary + matching helpers. No ML libraries here, so it is fast to import and easy to test.
import re

# Canonical skills the system knows about (what the JD and resume are scanned for).
TECH_SKILLS_DICT = [
    # Frontend & Web
    "javascript", "typescript", "react", "angular", "vue", "html", "css", "tailwind",
    "responsive design", "design systems", "wireframing", "prototyping", "figma", "adobe xd", "sketch",
    "user research", "usability testing",
    # Backend & Languages
    "python", "java", "c++", "c#", "nodejs", "fastapi", "flask", "django", "spring",
    "rest api", "graphql",
    # Data Science, ML & AI
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "tableau", "power bi", "excel", "statistics", "data visualization",
    "matplotlib", "seaborn", "jupyter", "spark", "hadoop", "airflow",
    "machine learning", "ai", "data science",
    # Databases & Storage
    "sql", "postgresql", "mysql", "mongodb", "redis",
    # Cloud, DevOps & Systems
    "aws", "azure", "gcp", "docker", "kubernetes", "linux", "bash",
    "terraform", "jenkins", "ci/cd", "git",
    # Agile & Process
    "agile", "scrum",
    # Broad concepts: satisfied by any specific member listed in GROUPS below
    "cloud", "databases",
]

# Other ways people write the same skill (alias -> canonical is built from this).
ALIASES = {
    "javascript": ["js", "java script"],
    "nodejs": ["node.js", "node js"],
    "react": ["reactjs", "react.js"],
    "vue": ["vuejs", "vue.js"],
    "angular": ["angularjs"],
    "postgresql": ["postgres"],
    "mongodb": ["mongo"],
    "kubernetes": ["k8s"],
    "machine learning": ["ml"],
    "ai": ["artificial intelligence"],
    "rest api": ["rest apis", "restful api", "restful apis"],
    "html": ["html5"],
    "css": ["css3"],
    "ci/cd": ["cicd", "ci cd"],
    "cloud": ["cloud computing"],
    "databases": ["database", "dbms"],
    "scikit-learn": ["sklearn", "scikit learn"],
    "tensorflow": [],
    "pytorch": ["torch"],
    "power bi": ["powerbi", "power-bi"],
    "statistics": ["statistical analysis", "statistical modeling"],
    "data visualization": ["data viz", "dataviz", "data visualisation"],
    "spring": ["spring boot"],
    "jupyter": ["jupyter notebook", "jupyter notebooks", "jupyter lab", "jupyterlab"],
    "spark": ["apache spark", "pyspark"],
    "hadoop": ["apache hadoop"],
    "airflow": ["apache airflow"],
    "bash": ["shell scripting", "bash scripting"],
    "excel": ["ms excel", "microsoft excel"],
    "linux": ["unix"],
    "sketch": [],
}

# Broad term -> specific skills that satisfy it.
GROUPS = {
    "cloud": {"aws", "azure", "gcp"},
    "databases": {"sql", "postgresql", "mysql", "mongodb", "redis"},
    "data visualization": {"tableau", "power bi", "matplotlib", "seaborn"},
    "sql": {"postgresql", "mysql"},
}

# Nicer names for the UI (anything not listed falls back to .title() or user's casing).
DISPLAY = {
    "aws": "AWS", "gcp": "GCP", "sql": "SQL", "css": "CSS", "html": "HTML", "ai": "AI",
    "nodejs": "Node.js", "javascript": "JavaScript", "typescript": "TypeScript",
    "postgresql": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB", "graphql": "GraphQL",
    "ci/cd": "CI/CD", "rest api": "REST API", "c++": "C++", "c#": "C#", "adobe xd": "Adobe XD",
    "scikit-learn": "Scikit-learn", "tensorflow": "TensorFlow", "pytorch": "PyTorch",
    "power bi": "Power BI", "pandas": "Pandas", "numpy": "NumPy", "excel": "Excel",
    "tableau": "Tableau", "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
    "spring": "Spring Boot", "redis": "Redis", "airflow": "Airflow", "jupyter": "Jupyter",
    "linux": "Linux", "bash": "Bash", "jenkins": "Jenkins", "terraform": "Terraform",
    "matplotlib": "Matplotlib", "seaborn": "Seaborn", "keras": "Keras", "spark": "Spark",
    "hadoop": "Hadoop", "statistics": "Statistical Analysis", "data visualization": "Data Visualization",
}

# --- Build lookup tables once at import ---
_ALIAS_TO_CANON = {}
for _canon in TECH_SKILLS_DICT:
    _ALIAS_TO_CANON[_canon] = _canon
    for _a in ALIASES.get(_canon, []):
        _ALIAS_TO_CANON[_a] = _canon

# Skills requiring capitalized case-sensitive matching plus guards against common English homographs
CASE_SENSITIVE_SKILLS = {
    "excel": ("Excel", r"(?!\s+(?:in|at)\b)"),
    "spring": ("Spring", r"(?!\s+\d{4}\b)"),
    "sketch": ("Sketch", ""),
    "spark": ("Spark", ""),
}

# A skill only matches as a WHOLE token: "ai" will not match inside "email",
# "java" will not match inside "javascript", "sql" will not match inside "mysql".
_PATTERNS = {}
for _canon in TECH_SKILLS_DICT:
    if _canon in CASE_SENSITIVE_SKILLS:
        _cap_name, _guard = CASE_SENSITIVE_SKILLS[_canon]
        _alias_list = ALIASES.get(_canon, [])
        _cap_regex = r"(?<![A-Za-z0-9+#.])" + re.escape(_cap_name) + _guard + r"(?![A-Za-z0-9+#])"
        if _alias_list:
            _alias_alt = "|".join(re.escape(n) for n in sorted(_alias_list, key=len, reverse=True))
            _alias_regex = r"(?<![A-Za-z0-9+#.])(?:" + _alias_alt + r")(?![A-Za-z0-9+#])"
            _PATTERNS[_canon] = (re.compile(_cap_regex), re.compile(_alias_regex, re.IGNORECASE))
        else:
            _PATTERNS[_canon] = (re.compile(_cap_regex), None)
    else:
        _names = [_canon] + ALIASES.get(_canon, [])
        _alt = "|".join(re.escape(n) for n in sorted(_names, key=len, reverse=True))
        _PATTERNS[_canon] = re.compile(r"(?<![A-Za-z0-9+#.])(?:" + _alt + r")(?![A-Za-z0-9+#])", re.IGNORECASE)


def find_skills(text: str) -> list[str]:
    """Return canonical skills that appear in the text as whole words."""
    found = []
    for skill, pat in _PATTERNS.items():
        if isinstance(pat, tuple):
            cap_pat, alias_pat = pat
            if cap_pat.search(text) or (alias_pat and alias_pat.search(text)):
                found.append(skill)
        else:
            if pat.search(text):
                found.append(skill)
    return found


def normalize_skill(name: str) -> str:
    """Map any alias ('Node.js', 'k8s') to its canonical form; unknown skills are just lowercased."""
    key = name.strip().lower()
    return _ALIAS_TO_CANON.get(key, key)


def expand_with_groups(skills: set) -> set:
    """Add broad concepts implied by specific skills (aws -> cloud)."""
    expanded = set(skills)
    for broad, members in GROUPS.items():
        if skills & members:
            expanded.add(broad)
    return expanded


def display_name(skill: str, original: str | None = None) -> str:
    """Return the display name for a skill, preserving original casing if unknown."""
    key = skill.strip().lower()
    if key in DISPLAY:
        return DISPLAY[key]
    if original and original.strip():
        return original.strip()
    return skill.title()
