import streamlit as st
import requests, io, re, os, base64
from datetime import datetime
from docx import Document
from typing import Dict, Any, Optional, List


# ---------------------------
# CONFIG - CHANGE THESE
# ---------------------------
GITHUB_OWNER = "Akhila-A2610"          # your GitHub username
GITHUB_REPO = "portfolio"             # your repo name (exact)
RESUME_PATH_IN_REPO = "Akhila_A_Resume.docx"  # resume docx path inside repo
BRANCH = "main"

# Optional local asset (stored in repo)
PROFILE_IMG = "assets/profile.jpg"


# ---------------------------
# Helpers: GitHub API + raw download
# ---------------------------
def get_github_commits_for_file(
    owner: str, repo: str, path: str, branch: str = "main", token: Optional[str] = None
) -> Optional[dict]:
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


def download_raw_file(
    owner: str, repo: str, path: str, branch: str = "main", token: Optional[str] = None
) -> Optional[bytes]:
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(raw_url, headers=headers, timeout=30)
    if r.status_code == 200:
        return r.content
    return None


def download_raw_text(
    owner: str, repo: str, path: str, branch: str = "main", token: Optional[str] = None
) -> Optional[str]:
    b = download_raw_file(owner, repo, path, branch, token)
    if not b:
        return None
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("utf-8", errors="replace")


# ---------------------------
# Parse .docx (tailored for your resume format)
# ---------------------------
def parse_resume_docx_bytes(docx_bytes: bytes) -> Dict[str, Any]:
    doc = Document(io.BytesIO(docx_bytes))

    # Paragraph lines
    para_lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]

    # Skills table: {Category: "skills, skills, ..."}
    skills_table: Dict[str, str] = {}
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) >= 2:
                left = cells[0].strip()
                right = cells[1].strip()
                if not left or not right:
                    continue
                # Skip a header row if present
                if left.lower() == "category" and right.lower().startswith("skil"):
                    continue
                skills_table[left] = right

    parsed: Dict[str, Any] = {
        "name": "",
        "role": "Senior Data Engineer | Data Scientist",  # default; you can hardcode your preferred title
        "contact_line": "",
        "summary": "",
        "skills": skills_table,            # dict
        "publications": [],                # list[str]
        "experience": {},                  # dict[str, list[str]]
        "education": [],                   # list[str]
        "certifications": []               # list[str]
    }

    if not para_lines:
        return parsed

    # Header
    parsed["name"] = para_lines[0]
    if len(para_lines) > 1:
        parsed["contact_line"] = para_lines[1]

    def clean_bullet(s: str) -> str:
        return s.replace("•", "").strip()

    HEADINGS = {
        "PROFESSIONAL SUMMARY": "summary",
        "TECHNICAL SKILLS": "skills",
        "PUBLICATIONS": "publications",
        "PROFESSIONAL EXPERIENCE": "experience",
        "EDUCATION": "education",
        "CERTIFICATIONS & ACHIEVEMENTS": "certifications",
        "CERTIFICATIONS": "certifications",
        "ACHIEVEMENTS": "certifications",
    }

    section: Optional[str] = None
    current_job: Optional[str] = None

    # Job header line pattern with dates like "Jan 2024 – Dec 2025" or "July 2019 - Mar 2023"
    job_header_re = re.compile(
        r""".+,\s*.+\s+((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*[–-]\s*
            (Present|((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})""",
        re.IGNORECASE | re.VERBOSE
    )

    i = 2  # after name + contact
    while i < len(para_lines):
        s = para_lines[i]
        s_u = s.upper().strip()

        # Switch section
        if s_u in HEADINGS:
            section = HEADINGS[s_u]
            current_job = None
            i += 1
            continue

        if section == "summary":
            parsed["summary"] += s + "\n"
            i += 1
            continue

        if section == "publications":
            if s.strip().startswith("•"):
                parsed["publications"].append(clean_bullet(s))
            else:
                if parsed["publications"]:
                    parsed["publications"][-1] += " " + s.strip()
                else:
                    parsed["publications"].append(s.strip())
            i += 1
            continue

        if section == "experience":
            # New job header
            if job_header_re.search(s) and "•" not in s:
                current_job = s.strip()
                parsed["experience"][current_job] = []
                i += 1
                continue

            # Bullet
            if current_job and s.strip().startswith("•"):
                parsed["experience"][current_job].append(clean_bullet(s))
                i += 1
                continue

            # Wrapped line
            if current_job and parsed["experience"][current_job]:
                parsed["experience"][current_job][-1] += " " + s.strip()
                i += 1
                continue

            i += 1
            continue

        if section == "education":
            parsed["education"].append(s.strip())
            i += 1
            continue

        if section == "certifications":
            if s.strip().startswith("•"):
                parsed["certifications"].append(clean_bullet(s))
            else:
                if parsed["certifications"]:
                    parsed["certifications"][-1] += " " + s.strip()
                else:
                    parsed["certifications"].append(s.strip())
            i += 1
            continue

        i += 1

    parsed["summary"] = parsed["summary"].strip()
    return parsed


# ---------------------------
# Projects loader (projects.docx in repo root)
# ---------------------------
def load_projects_from_github(owner: str, repo: str, branch: str = "main", token: Optional[str] = None) -> str:
    projects_path = "projects.docx"
    content_bytes = download_raw_file(owner, repo, projects_path, branch, token)
    if not content_bytes:
        return "projects.docx not found in your GitHub repo root."

    doc = Document(io.BytesIO(content_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join([f"• {p}" for p in paragraphs])


# ---------------------------
# Load resume from GitHub (cache in Streamlit, not on disk)
# ---------------------------
@st.cache_data(show_spinner=False)
def load_resume_from_github(owner: str, repo: str, path: str, branch: str = "main", token: Optional[str] = None) -> Dict[str, Any]:
    content_bytes = download_raw_file(owner, repo, path, branch, token)
    if content_bytes is None:
        raise RuntimeError("Could not download resume file from GitHub (check file name/path).")
    return parse_resume_docx_bytes(content_bytes)


# ---------------------------
# Contact hyperlinks
# ---------------------------
def make_hyperlinked_contact(contact_text: str, linkedin_url: str, github_url: str) -> str:
    if not contact_text:
        return ""

    # email
    email_pattern = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
    contact_text = email_pattern.sub(
        lambda m: f'<a href="mailto:{m.group(0)}" style="color:#87CEFA;">{m.group(0)}</a>',
        contact_text
    )

    # LinkedIn and GitHub keyword replacement
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

    # normalize separators
    contact_text = contact_text.replace("|", "&nbsp;|&nbsp;")
    return contact_text


# ---------------------------
# UI helpers
# ---------------------------
def css():
    st.markdown("""
    <style>
      .stApp { background-color: #0b0f19; color: white; }
      h1, h2, h3 { letter-spacing: 0.2px; }
      .muted { color: #b9c0d4; }

      .sticky {
        position: fixed;
        top: 0; left: 0; width: 100%;
        background: rgba(11,15,25,0.92);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid rgba(255,255,255,0.08);
        z-index: 999;
        padding: 14px 18px;
      }
      .header-row {
        display:flex; align-items:center; justify-content:space-between; gap:18px;
        max-width: 1200px; margin: 0 auto;
      }
      .id-row { display:flex; align-items:center; gap:14px; }
      .avatar {
        width: 56px; height: 56px; border-radius: 50%;
        object-fit: cover;
        border: 2px solid rgba(135,206,250,0.6);
      }

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


def card(title: str, body_html: str):
    st.markdown(f"""
    <div class="card">
      <div style="font-size:20px;font-weight:800;margin-bottom:8px;">{title}</div>
      <div class="muted" style="font-size:15px;line-height:1.6;">{body_html}</div>
    </div>
    """, unsafe_allow_html=True)


# ---------------------------
# Main app
# ---------------------------
def main():
    st.set_page_config(page_title="Akhila — Portfolio", layout="wide")
    css()

    # Refresh button (clear cache)
    col1, col2 = st.columns([1, 6])
    with col1:
        if st.button("🔄 Refresh"):
            st.cache_data.clear()
            st.rerun()

    # Token (optional; only needed for private repo)
    token = None
    try:
        token = st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        token = None

    with st.spinner("Loading resume from GitHub..."):
        resume = load_resume_from_github(GITHUB_OWNER, GITHUB_REPO, RESUME_PATH_IN_REPO, BRANCH, token)

    # Profile image
    profile_img_b64 = None
    if os.path.exists(PROFILE_IMG):
        with open(PROFILE_IMG, "rb") as img_file:
            profile_img_b64 = base64.b64encode(img_file.read()).decode()

    # Links
    linkedin_url = "https://www.linkedin.com/in/akhilaakkala/"
    github_url = f"https://github.com/{GITHUB_OWNER}"
    contact_html = make_hyperlinked_contact(resume.get("contact_line", ""), linkedin_url, github_url)

    render_sticky_header(
        name=resume.get("name", "Akhila A"),
        role=resume.get("role", "Senior Data Engineer | Data Scientist"),
        contact_html=contact_html,
        profile_img_b64=profile_img_b64
    )

    # SUMMARY
    section_anchor("summary")
    summary_text = (resume.get("summary", "") or "").strip()
    if summary_text:
        bullets = [s.strip() for s in re.split(r'(?<=[.!?])\s+', summary_text) if s.strip()]
        card("Professional Summary", "<br>".join([f"• {b}" for b in bullets]))
    else:
        card("Professional Summary", "No summary found in the resume.")

    # SKILLS (chips by category)
    section_anchor("skills")
    skills = resume.get("skills", {}) or {}
    if isinstance(skills, dict) and skills:
        st.markdown("<div class='card'><div style='font-size:20px;font-weight:800;margin-bottom:8px;'>Skills</div></div>", unsafe_allow_html=True)
        for cat, val in skills.items():
            items = [x.strip() for x in re.split(r"[,\n]+", val) if x.strip()]
            chips = " ".join([f"<span class='chip'>{x}</span>" for x in items])
            st.markdown(
                f"<div class='card'><div style='font-weight:800;margin-bottom:8px;'>{cat}</div>{chips}</div>",
                unsafe_allow_html=True
            )
    else:
        card("Skills", "Could not read skills table from the DOCX.")

    # EXPERIENCE
    section_anchor("experience")
    st.markdown("<div class='card'><div style='font-size:20px;font-weight:800;margin-bottom:8px;'>Work Experience</div><div class='muted'>Click a role to view details.</div></div>", unsafe_allow_html=True)

    exp = resume.get("experience", {}) or {}
    if exp:
        for job_header, bullets in exp.items():
            with st.expander(job_header, expanded=False):
                if bullets:
                    st.markdown("\n".join([f"- {b}" for b in bullets]))
                else:
                    st.write("No bullet points found for this role.")
    else:
        st.info("No experience parsed yet. Make sure bullets start with • in the DOCX.")

    # PUBLICATIONS (FIXED: list -> render)
    section_anchor("publications")
    pubs = resume.get("publications", []) or []
    if isinstance(pubs, list) and pubs:
        card("Publications", "<br>".join([f"• {p}" for p in pubs]))
    else:
        card("Publications", "No publications found.")

    # CERTIFICATIONS
    section_anchor("certs")
    certs = resume.get("certifications", []) or []
    if certs:
        card("Certifications", "<br>".join([f"• {c}" for c in certs]))
    else:
        card("Certifications", "No certifications found.")

    # EDUCATION
    section_anchor("education")
    edu = resume.get("education", []) or []
    if edu:
        card("Education", "<br>".join([f"• {e}" for e in edu]))
    else:
        card("Education", "No education found.")

    # PROJECTS
    section_anchor("projects")
    projects_text = load_projects_from_github(GITHUB_OWNER, GITHUB_REPO, BRANCH, token)
    card("Projects", projects_text.replace("\n", "<br>"))

    # ABOUT (load from GitHub)
    section_anchor("about")
    about_txt = download_raw_text(GITHUB_OWNER, GITHUB_REPO, "aboutpage.txt", BRANCH, token)
    if about_txt:
        card("About This Page", about_txt.replace("\n", "<br>"))
    else:
        card("About This Page", "aboutpage.txt not found in your GitHub repo root.")


if __name__ == "__main__":
    main()
