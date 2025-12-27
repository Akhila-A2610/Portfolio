import streamlit as st
import requests, io, re, os, json, base64
from datetime import datetime
from docx import Document
from typing import Dict, Any, Optional

# ---------------------------
# CONFIG - CHANGE THESE
# ---------------------------
GITHUB_OWNER = "Akhila-A2610"          # <-- your GitHub username
GITHUB_REPO = "portfolio"            # <-- your repo name
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
    lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    # --- ALSO read table content (for skills tables) ---
    table_lines = []
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                t = cell.text.strip()
                if t:
                    table_lines.append(t)

    lines = lines + table_lines


    parsed = {
        "name": "",
        "role": "",
        "contact_line": "",
        "summary": "",
        "skills": "",
        "publications": "",
        "experience": {},
        "certifications": [],
        "education": []
    }

    if not lines:
        return parsed

    # Header (based on your resume)
    parsed["name"] = lines[0]
    if len(lines) > 1:
        parsed["contact_line"] = lines[1]

    # Section detection
    def is_heading(s: str) -> bool:
        s_u = s.strip().upper()
        return s_u in {
            "PROFESSIONAL SUMMARY",
            "TECHNICAL SKILLS",
            "PUBLICATIONS",
            "PROFESSIONAL EXPERIENCE",
            "EDUCATION",
            "CERTIFICATIONS & ACHIEVEMENTS",
            "CERTIFICATIONS",
            "ACHIEVEMENTS"
        }

    section = None
    current_job = None

    for s in lines[2:]:
        s_u = s.upper().strip()

        # Map headings to sections
        if s_u == "PROFESSIONAL SUMMARY":
            section = "summary"
            continue
        if s_u == "TECHNICAL SKILLS":
            section = "skills"
            continue
        if s_u == "PUBLICATIONS":
            section = "publications"
            continue
        if s_u == "PROFESSIONAL EXPERIENCE":
            section = "experience"
            continue
        if s_u == "EDUCATION":
            section = "education"
            continue
        if s_u in {"CERTIFICATIONS & ACHIEVEMENTS", "CERTIFICATIONS", "ACHIEVEMENTS"}:
            section = "certifications"
            continue

        # Content parsing per section
        if section == "summary":
            parsed["summary"] += s + "\n"

        elif section == "skills":
            # your skills section is a table-like structure in docx; we just collect text lines
            parsed["skills"] += s + "\n"

        elif section == "publications":
            parsed["publications"] += s + "\n"

        elif section == "education":
            parsed["education"].append(s)

        elif section == "certifications":
            # strip leading bullet if present
            parsed["certifications"].append(s.lstrip("•").strip())

        elif section == "experience":
            # Detect a new job line (your resume has: "Title, Company, Location  Jan 2024 – Dec 2025")
            # Heuristic: contains a date dash like "–" or "-" with years
            if re.search(r"\b(19|20)\d{2}\b", s) and ("–" in s or "-" in s):
                current_job = s
                parsed["experience"][current_job] = ""
                continue

            # Add bullet lines under the current job
            if current_job:
                parsed["experience"][current_job] += s.lstrip("•").strip() + "\n"

    # Role fallback (optional)
    # If you want a role on the header but it isn't explicitly in DOCX, infer from summary first line.
    if not parsed["role"]:
        first_summary_line = parsed["summary"].strip().split("\n")[0] if parsed["summary"].strip() else ""
        if "Senior" in first_summary_line or "Engineer" in first_summary_line or "Scientist" in first_summary_line:
            parsed["role"] = "Senior Data Engineer | Data Scientist"
        else:
            parsed["role"] = "Data Engineer | Data Scientist"

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
def css():
    st.markdown("""
    <style>
      .stApp { background-color: #0b0f19; color: white; }

      /* general typography */
      h1, h2, h3 { letter-spacing: 0.2px; }
      .muted { color: #b9c0d4; }

      /* sticky header */
      .sticky {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        background: rgba(11,15,25,0.92);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid rgba(255,255,255,0.08);
        z-index: 999;
        padding: 14px 18px;
      }
      .header-row {
        display:flex; align-items:center; justify-content:space-between; gap: 18px;
        max-width: 1200px; margin: 0 auto;
      }
      .id-row { display:flex; align-items:center; gap: 14px; }
      .avatar { width: 56px; height: 56px; border-radius: 50%; object-fit: cover; border: 2px solid rgba(135,206,250,0.6); }

      .nav a {
        display:inline-block;
        background: rgba(23,162,184,0.95);
        color: white !important;
        text-decoration:none !important;
        padding: 7px 10px;
        border-radius: 10px;
        margin-left: 8px;
        font-weight: 650;
        font-size: 13px;
      }
      .nav a:hover { background: rgba(2,79,156,0.95); }

      .spacer { height: 96px; }

      /* section cards */
      .card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        padding: 18px 18px;
        margin: 12px 0;
      }
      .chip {
        display:inline-block;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(135,206,250,0.12);
        border: 1px solid rgba(135,206,250,0.25);
        margin: 4px 6px 0 0;
        font-size: 13px;
      }

      /* make anchors not hide behind sticky header */
      a[id] { scroll-margin-top: 110px; }
    </style>
    """, unsafe_allow_html=True)

def render_sticky_header(name, role, contact_html, profile_img_b64=None):
    avatar_html = ""
    if profile_img_b64:
        avatar_html = f"<img class='avatar' src='data:image/jpeg;base64,{profile_img_b64}' />"

    st.markdown(f"""
    <div class="sticky">
      <div class="header-row">
        <div class="id-row">
          {avatar_html}
          <div>
            <div style="font-size:26px;font-weight:800;color:gold;line-height:1.1;">{name}</div>
            <div style="font-size:15px;font-weight:700;color:limegreen;line-height:1.2;">{role}</div>
            <div class="muted" style="margin-top:3px;">{contact_html}</div>
          </div>
        </div>
        <div class="nav">
          <a href="#summary">Summary</a>
          <a href="#skills">Skills</a>
          <a href="#experience">Experience</a>
          <a href="#publications">Publications</a>
          <a href="#certs">Certifications</a>
          <a href="#education">Education</a>
          <a href="#projects">Projects</a>
          <a href="#about">About</a>
        </div>
      </div>
    </div>
    <div class="spacer"></div>
    """, unsafe_allow_html=True)

def section_anchor(anchor_id: str):
    st.markdown(f'<a id="{anchor_id}"></a>', unsafe_allow_html=True)

def card(title: str, body_md: str):
    st.markdown(f"""
    <div class="card">
      <div style="font-size:20px;font-weight:800;margin-bottom:8px;">{title}</div>
      <div class="muted" style="font-size:15px;line-height:1.6;">{body_md}</div>
    </div>
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="Akhila — Portfolio", layout="wide")
    css()

    token = None
    try:
        token = st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        token = None

    with st.spinner("Loading resume from GitHub..."):
        resume = load_resume_from_github(GITHUB_OWNER, GITHUB_REPO, RESUME_PATH_IN_REPO, BRANCH, token)

    # Profile image (optional)
    profile_img_b64 = None
    if os.path.exists(PROFILE_IMG):
        with open(PROFILE_IMG, "rb") as img_file:
            profile_img_b64 = base64.b64encode(img_file.read()).decode()

    # Links
    linkedin_url = "https://www.linkedin.com/in/akhilaakkala/"  # <-- change
    github_url = f"https://github.com/{GITHUB_OWNER}"
    contact_html = make_hyperlinked_contact(resume.get("contact_line",""), linkedin_url, github_url)

    # Sticky header
    render_sticky_header(
        name=resume.get("name","Akhila A"),
        role=resume.get("role","Senior Data Engineer | Data Scientist"),
        contact_html=contact_html,
        profile_img_b64=profile_img_b64
    )

    # SUMMARY
    section_anchor("summary")
    summary_text = (resume.get("summary","") or "").strip()
    if summary_text:
        bullets = [s.strip() for s in re.split(r'(?<=[.!?])\s+', summary_text) if s.strip()]
        card("Professional Summary", "<br>".join([f"• {b}" for b in bullets]))
    else:
        card("Professional Summary", "Add a **Professional Summary** section in your DOCX.")

    # SKILLS (display as chips)
    section_anchor("skills")
    skills_text = (resume.get("skills","") or "").strip()
    if skills_text:
        # split by commas and newlines, keep it simple
        raw = re.split(r"[,\n]+", skills_text)
        skills = [s.strip() for s in raw if s.strip() and len(s.strip()) < 60]
        chips = " ".join([f"<span class='chip'>{s}</span>" for s in skills[:60]])
        st.markdown(f"<div class='card'><div style='font-size:20px;font-weight:800;margin-bottom:8px;'>Skills</div>{chips}</div>", unsafe_allow_html=True)
    else:
        card("Skills", "Add **Technical Skills** content in your DOCX.")

    # EXPERIENCE
    section_anchor("experience")
    st.markdown("<div class='card'><div style='font-size:20px;font-weight:800;margin-bottom:8px;'>Work Experience</div></div>", unsafe_allow_html=True)
    exp = resume.get("experience", {}) or {}
    if exp:
        for job_title_line, details in exp.items():
            with st.expander(job_title_line, expanded=False):
                lines = [l.strip() for l in (details or "").split("\n") if l.strip()]
                st.markdown("\n".join([f"- {l}" for l in lines]))
    else:
        st.info("No experience parsed yet — make sure your DOCX has a **Professional Experience** heading and job lines with dates.")

    # PUBLICATIONS
    section_anchor("publications")
    pubs = (resume.get("publications","") or "").strip()
    if pubs:
        card("Publications", pubs.replace("\n", "<br>"))
    else:
        card("Publications", "Add your **Publications** section in the DOCX (or leave it out).")

    # CERTIFICATIONS
    section_anchor("certs")
    certs = resume.get("certifications", []) or []
    if certs:
        card("Certifications", "<br>".join([f"• {c}" for c in certs]))
    else:
        card("Certifications", "Add **Certifications & Achievements** section in your DOCX.")

    # EDUCATION
    section_anchor("education")
    edu = resume.get("education", []) or []
    if edu:
        card("Education", "<br>".join([f"• {e}" for e in edu]))
    else:
        card("Education", "Add **Education** section in your DOCX.")

    # PROJECTS
    section_anchor("projects")
    card("Projects", load_projects_from_github(GITHUB_OWNER, GITHUB_REPO, BRANCH, token).replace("\n", "<br>"))

    # ABOUT
    section_anchor("about")
    if os.path.exists("aboutpage.txt"):
        with open("aboutpage.txt", "r", encoding="utf-8") as f:
            card("About This Page", f.read().replace("\n", "<br>"))
    else:
        card("About This Page", "Add **aboutpage.txt** to your repo root (same folder as app.py).")
    

if __name__ == "__main__":
    main()
