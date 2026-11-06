# backend/skills.py
# Skill vocabulary + matching helpers. No ML libraries here, so it is fast to import and easy to test.
import re

# Canonical skills the system knows about (what the JD and resume are scanned for).
TECH_SKILLS_DICT = [
    "python", "java", "javascript", "react", "angular", "vue", "nodejs",
    "sql", "postgresql", "mysql", "mongodb", "aws", "azure", "gcp", "docker", "kubernetes",
    "git", "figma", "adobe xd", "sketch", "html", "css", "tailwind", "typescript", "c++", "c#",
    "machine learning", "ai", "data science", "rest api", "graphql", "ci/cd", "agile", "scrum",
    "wireframing", "prototyping", "user research", "usability testing", "design systems",
    "responsive design",
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
}

# Broad term -> specific skills that satisfy it.
# If the resume has AWS, the resume implicitly covers "Cloud".
GROUPS = {
    "cloud": {"aws", "azure", "gcp"},
    "databases": {"sql", "postgresql", "mysql", "mongodb"},
}

# Nicer names for the UI (anything not listed falls back to .title()).
DISPLAY = {
    "aws": "AWS", "gcp": "GCP", "sql": "SQL", "css": "CSS", "html": "HTML", "ai": "AI",
    "nodejs": "Node.js", "javascript": "JavaScript", "typescript": "TypeScript",
    "postgresql": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB", "graphql": "GraphQL",
    "ci/cd": "CI/CD", "rest api": "REST API", "c++": "C++", "c#": "C#", "adobe xd": "Adobe XD",
}

# --- Build lookup tables once at import ---
_ALIAS_TO_CANON = {}
for _canon in TECH_SKILLS_DICT:
    _ALIAS_TO_CANON[_canon] = _canon
    for _a in ALIASES.get(_canon, []):
        _ALIAS_TO_CANON[_a] = _canon

# A skill only matches as a WHOLE token: "ai" will not match inside "email",
# "java" will not match inside "javascript", "sql" will not match inside "mysql".
_PATTERNS = {}
for _canon in TECH_SKILLS_DICT:
    _names = [_canon] + ALIASES.get(_canon, [])
    _alt = "|".join(re.escape(n) for n in sorted(_names, key=len, reverse=True))
    _PATTERNS[_canon] = re.compile(r"(?<![A-Za-z0-9+#.])(?:" + _alt + r")(?![A-Za-z0-9+#])", re.IGNORECASE)


def find_skills(text: str) -> list[str]:
    """Return canonical skills that appear in the text as whole words."""
    return [skill for skill, pat in _PATTERNS.items() if pat.search(text)]


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


def display_name(skill: str) -> str:
    return DISPLAY.get(skill, skill.title())