import streamlit as st
import requests, io, re, os, json, base64
from datetime import datetime
from docx import Document
from typing import Dict, Any, Optional

# ---------------------------
# CONFIG - CHANGE THESE
# ---------------------------
GITHUB_OWNER = "Akhila-A2610"          # <-- your GitHub username
GITHUB_REPO = "Portfolio"            # <-- your repo name
RESUME_PATH_IN_REPO = "Akhila_A_Resume.docx"  # <-- your resume docx inside repo
BRANCH = "main"
JSON_CACHE = "resume_cache.json"      # safer name than resume_data.json

# Optional local assets (stored in repo)
PROFILE_IMG = "assets/profile.jpg"

# If you don't have logos yet, keep these empty to avoid missing-file issues
COMPANY_LOGOS = {}   # You can add later
CERT_LOGOS = {}      # You can add later
EDU_LOGO = {}        # You can add later

# ---------------------------
# Helpers: GitHub API + raw download
# ---------------------------
def get_github_commits_for_file(owner: str, repo: str, path: str, branch: str = "main", token: Optional[str] = None) -> Optional[dict]:
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    params = {"path": path, "sha": branch, "per_page": 1}
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(url, params=params, headers=headers, timeout=15)
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, list) and data:
            return data[0]
    return None

def download_raw_file(owner: str, repo: str, path: str, branch: str = "main", token: Optional[str] = None) -> Optional[bytes]:
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(raw_url, headers=headers, timeout=30)
    if r.status_code == 200:
        return r.content
    return None

# ---------------------------
# Parse .docx (simple parser)
# ---------------------------
def parse_resume_docx_bytes(docx_bytes: bytes) -> Dict[str, Any]:
    doc = Document(io.BytesIO(docx_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]

    parsed = {
        "name": "",
        "role": "",
        "contact_line": "",
        "summary": "",
        "skills": "",
        "experience": {},
        "certifications": [],
        "education": []
    }

    # Basic header lines (you can keep your resume format like this)
    if len(paragraphs) >= 1:
        parsed["name"] = paragraphs[0]
    if len(paragraphs) >= 2:
        parsed["role"] = paragraphs[1]
    if len(paragraphs) >= 3:
        parsed["contact_line"] = paragraphs[2]

    section = None
    current_company = None

    for txt in paragraphs[3:]:
        upper = txt.upper()

        if upper.startswith("PROFESSIONAL SUMMARY"):
            section = "summary"; continue
        if upper.startswith("SKILLS"):
            section = "skills"; continue
        if upper.startswith("PROFESSIONAL EXPERIENCE"):
            section = "experience"; continue
        if upper.startswith("CERTIFICATIONS"):
            section = "certifications"; continue
        if upper.startswith("EDUCATION"):
            section = "education"; continue

        # Experience company marker
        if section == "experience" and txt.startswith("Client:"):
            current_company = txt.replace("Client:", "").strip()
            parsed["experience"][current_company] = ""
            continue

        if section == "summary":
            parsed["summary"] += txt + "\n"
        elif section == "skills":
            parsed["skills"] += txt + "\n"
        elif section == "experience":
            if current_company:
                parsed["experience"][current_company] += txt + "\n"
        elif section == "certifications":
            parsed["certifications"].append(txt)
        elif section == "education":
            parsed["education"].append(txt)

    return parsed

# ---------------------------
# Projects parser (projects.docx in repo)
# ---------------------------
def load_projects_from_github(owner: str, repo: str, branch: str = "main", token: Optional[str] = None) -> str:
    projects_path = "projects.docx"
    content_bytes = download_raw_file(owner, repo, projects_path, branch, token)
    if not content_bytes:
        return "Projects file not found in repo."

    doc = Document(io.BytesIO(content_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join([f"- {p}" for p in paragraphs])

# ---------------------------
# Load resume from GitHub + cache if unchanged
# ---------------------------
@st.cache_data(show_spinner=False)
def load_resume_from_github(owner: str, repo: str, path: str, branch: str = "main", token: Optional[str] = None) -> Dict[str, Any]:
    commit = get_github_commits_for_file(owner, repo, path, branch, token)
    commit_iso = None
    if commit:
        commit_iso = commit.get("commit", {}).get("committer", {}).get("date") or commit.get("commit", {}).get("author", {}).get("date")

    # If local cache exists and matches last commit, use it
    if os.path.exists(JSON_CACHE):
        try:
            with open(JSON_CACHE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if commit_iso and cached.get("last_updated") == commit_iso:
                return cached["content"]
        except Exception:
            pass

    content_bytes = download_raw_file(owner, repo, path, branch, token)
    if content_bytes is None:
        raise RuntimeError("Could not download resume file from GitHub (check file name/path).")

    parsed = parse_resume_docx_bytes(content_bytes)

    last_updated = commit_iso or datetime.utcnow().isoformat()
    with open(JSON_CACHE, "w", encoding="utf-8") as f:
        json.dump({"last_updated": last_updated, "content": parsed}, f, indent=2)

    return parsed

# ---------------------------
# Contact hyperlinks
# ---------------------------
def make_hyperlinked_contact(contact_text: str, linkedin_url: str, github_url: str) -> str:
    if not contact_text:
        return ""

    email_pattern = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
    contact_text = email_pattern.sub(
        lambda m: f'<a href="mailto:{m.group(0)}" style="color:#87CEFA;">{m.group(0)}</a>',
        contact_text
    )

    contact_text = re.sub(
        r'\bLinkedIn\b',
        f'<a href="{linkedin_url}" target="_blank" style="color:#87CEFA;">LinkedIn</a>',
        contact_text,
        flags=re.IGNORECASE
    )

    contact_text = re.sub(
        r'\bGitHub\b',
        f'<a href="{github_url}" target="_blank" style="color:#87CEFA;">GitHub</a>',
        contact_text,
        flags=re.IGNORECASE
    )

    contact_text = contact_text.replace("|", "&nbsp;|&nbsp;")
    return contact_text

# ---------------------------
# Main UI
# ---------------------------
def main():
    st.set_page_config(page_title="Akhila — Portfolio", layout="wide")

    # Optional: token for private repos (yours is public, so not required)
    token = None
    try:
        token = st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        token = None

    st.markdown("<style>.stApp{background-color:black;color:white;}</style>", unsafe_allow_html=True)

    with st.spinner("Loading resume from GitHub..."):
        resume = load_resume_from_github(GITHUB_OWNER, GITHUB_REPO, RESUME_PATH_IN_REPO, BRANCH, token)

    # Header
    profile_img_tag = ""
    if os.path.exists(PROFILE_IMG):
        with open(PROFILE_IMG, "rb") as img_file:
            img_b64 = base64.b64encode(img_file.read()).decode()
            profile_img_tag = f"<img src='data:image/jpeg;base64,{img_b64}' width='80'>"

    linkedin_url = "https://www.linkedin.com/in/YOUR_LINKEDIN/"
    github_url = f"https://github.com/{GITHUB_OWNER}"

    contact_html = make_hyperlinked_contact(resume.get("contact_line",""), linkedin_url, github_url)

    st.markdown(f"""
    <div style="display:flex; gap:20px; align-items:center; border-bottom:2px solid #87CEFA; padding-bottom:10px;">
        {profile_img_tag}
        <div>
            <h1 style="margin:0;color:gold;">{resume.get("name","")}</h1>
            <h2 style="margin:0;color:limegreen;">{resume.get("role","")}</h2>
            <p style="margin:0;">{contact_html}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("## Professional Summary")
    summary_text = resume.get("summary","").strip()
    if summary_text:
        bullets = [s.strip() for s in re.split(r'(?<=[.!?])\s+', summary_text) if s.strip()]
        st.markdown("\n".join([f"- {b}" for b in bullets]))
    else:
        st.write("No summary found.")

    st.markdown("## Skills")
    st.write(resume.get("skills","").strip() or "No skills found.")

    st.markdown("## Work Experience")
    exp = resume.get("experience", {})
    if exp:
        for comp, details in exp.items():
            with st.expander(comp, expanded=False):
                lines = [l.strip() for l in details.split("\n") if l.strip()]
                st.markdown("\n".join([f"- {l}" for l in lines]))
    else:
        st.write("No experience found.")

    st.markdown("## Certifications")
    certs = resume.get("certifications", [])
    if certs:
        st.markdown("\n".join([f"- {c}" for c in certs]))
    else:
        st.write("No certifications found.")

    st.markdown("## Education")
    edu = resume.get("education", [])
    if edu:
        st.markdown("\n".join([f"- {e}" for e in edu]))
    else:
        st.write("No education found.")

    st.markdown("## Projects")
    st.markdown(load_projects_from_github(GITHUB_OWNER, GITHUB_REPO, BRANCH, token))

    st.markdown("## About This Page")
    if os.path.exists("aboutpage.txt"):
        with open("aboutpage.txt", "r", encoding="utf-8") as f:
            st.write(f.read())
    else:
        st.write("aboutpage.txt not found.")

if __name__ == "__main__":
    main()
