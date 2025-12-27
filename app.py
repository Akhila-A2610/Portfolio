import streamlit as st
import requests, io, re, os, base64
from docx import Document
from typing import Dict, Any, Optional

# ======================================================
# MUST BE FIRST STREAMLIT COMMAND (KEEP ONLY ONCE)
# ======================================================
st.set_page_config(page_title="Akhila — Portfolio", layout="wide")

# ---------------------------
# CONFIG - CHANGE THESE
# ---------------------------
GITHUB_OWNER = "Akhila-A2610"
GITHUB_REPO = "portfolio"
RESUME_PATH_IN_REPO = "Akhila_A_Resume.docx"


BRANCH = "main"

# Optional local asset (stored in repo)
PROFILE_IMG = "assets/profile.jpg"
COMPANY_LOGOS = {
    "Utah State University": "assets/company_logos/usu.jfif",
    "LTIMindtree": "assets/company_logos/ltimindtree.png",
    "Tata Consultancy Services (TCS)": "assets/company_logos/tcs.jfif"
}


# ---------------------------
# Helpers: GitHub raw download
# ---------------------------
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

    para_lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]

    # Skills table
    skills_table: Dict[str, str] = {}
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) >= 2:
                left = cells[0].strip()
                right = cells[1].strip()
                if not left or not right:
                    continue
                if left.lower() == "category" and right.lower().startswith("skil"):
                    continue
                skills_table[left] = right

    parsed: Dict[str, Any] = {
        "name": "",
        "role": "Senior Data Engineer | Data Scientist",
        "contact_line": "",
        "summary": "",
        "skills": skills_table,
        "publications": [],
        "experience": {},
        "education": [],
        "certifications": [],
    }

    if not para_lines:
        return parsed

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

    job_header_re = re.compile(
        r""".+,\s*.+\s+
            ((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)
            |January|February|March|April|May|June|July|August|September|October|November|December)
            \s+\d{4}\s*[–-]\s*
            (Present|
            ((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)
            |January|February|March|April|May|June|July|August|September|October|November|December)
            \s+\d{4})
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    i = 2
    while i < len(para_lines):
        s = para_lines[i]
        s_u = s.upper().strip()

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
            if job_header_re.search(s) and "•" not in s:
                current_job = s.strip()
                parsed["experience"][current_job] = []
                i += 1
                continue

            if current_job and s.strip().startswith("•"):
                parsed["experience"][current_job].append(clean_bullet(s))
                i += 1
                continue

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

#----------------------------
# Company logos
#----------------------------
def pick_company_key(job_header: str, logo_map: Dict[str, str]) -> Optional[str]:
    """Return the first logo_map key that appears inside job_header (case-insensitive)."""
    j = job_header.lower()
    for k in logo_map.keys():
        if k.lower() in j:
            return k
    return None


def render_experience_with_logos(experience: Dict[str, list], logo_map: Dict[str, str]):
    """
    Shows company logos as clickable cards/buttons.
    Clicking one shows that job's bullets in an expander area.
    """
    if "selected_job" not in st.session_state:
        st.session_state["selected_job"] = None

    job_headers = list(experience.keys())
    if not job_headers:
        st.info("No experience parsed.")
        return

    # Build "company groups" (optional): pick the company key for each job header
    items = []
    for jh in job_headers:
        ck = pick_company_key(jh, logo_map)
        logo_path = logo_map.get(ck) if ck else None
        items.append((jh, ck, logo_path))

    st.markdown("<div class='card'><div style='font-size:20px;font-weight:800;'>Work Experience</div><div class='muted'>Click a company to view details.</div></div>", unsafe_allow_html=True)

    # show logos in a row (responsive-ish)
    cols = st.columns(min(4, len(items)))
    for idx, (job_header, company_key, logo_path) in enumerate(items):
        with cols[idx % len(cols)]:
            if logo_path and os.path.exists(logo_path):
                st.image(logo_path, width=90)

            # Button label: company name if found, else shorten header
            label = company_key if company_key else job_header[:28] + ("..." if len(job_header) > 28 else "")
            if st.button(label, key=f"job_btn_{idx}"):
                st.session_state["selected_job"] = job_header

    # Show selected job details
    selected = st.session_state.get("selected_job")
    if selected:
        bullets = experience.get(selected, [])
        with st.expander(selected, expanded=True):
            if bullets:
                st.markdown("\n".join([f"- {b}" for b in bullets]))
            else:
                st.write("No bullet points found.")
            if st.button("Close", key="close_job"):
                st.session_state["selected_job"] = None



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
# Load resume from GitHub (Streamlit cache)
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

    email_pattern = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
    contact_text = email_pattern.sub(
        lambda m: f'<a href="mailto:{m.group(0)}" style="color:#87CEFA;text-decoration:none;">{m.group(0)}</a>',
        contact_text,
    )

    contact_text = re.sub(
        r"\bLinkedIn\b",
        f'<a href="{linkedin_url}" target="_blank" style="color:#87CEFA;text-decoration:none;">LinkedIn</a>',
        contact_text,
        flags=re.IGNORECASE,
    )
    contact_text = re.sub(
        r"\bGitHub\b",
        f'<a href="{github_url}" target="_blank" style="color:#87CEFA;text-decoration:none;">GitHub</a>',
        contact_text,
        flags=re.IGNORECASE,
    )

    contact_text = contact_text.replace("|", "&nbsp;|&nbsp;")
    return contact_text


# ---------------------------
# UI helpers
# ---------------------------
def css():
    st.markdown(
        """
<style>
/* Hide Streamlit top chrome (new + old selectors) */
header { visibility: hidden; height: 0px; }
footer { visibility: hidden; height: 0px; }
[data-testid="stHeader"] { display: none; }
[data-testid="stToolbar"] { display: none; }

/* Remove default top padding/blank space */
.main .block-container { padding-top: 0rem !important; }
section.main > div { padding-top: 0rem !important; }
div.block-container { padding-top: 0rem !important; }

/* IMPORTANT: prevent Streamlit from showing our HTML inside code-style containers */
div[data-testid="stMarkdownContainer"] pre { display: none !important; }

/* Theme */
.stApp { background-color: #0b0f19; color: white; }
.muted { color: #b9c0d4; }

/* Sticky header */
.sticky {
  position: fixed;
  top: 0; left: 0;
  width: 100%;
  background: rgba(11,15,25,0.96);
  backdrop-filter: blur(10px);
  border-bottom: 2px solid rgba(135,206,250,0.75);
  z-index: 9999;
  padding: 14px 18px;
}

.header-row {
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap: 18px;
  max-width: 1200px;
  margin: 0 auto;
}

.id-row { display:flex; align-items:center; gap:14px; min-width: 360px; }

.avatar {
  width: 74px;
  height: 74px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid rgba(135,206,250,0.75);
}

.nav {
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  justify-content:flex-end;
  padding-top:6px;
  max-width:560px;
}

.nav a {
  background:#11a9c0;
  color:white !important;
  text-decoration:none !important;
  padding:10px 14px;
  border-radius:8px;
  font-weight:800;
  font-size:14px;
  white-space:nowrap;
}
.nav a:hover { background:#02839a; }

/* Spacer pushes content below sticky header */
.spacer { height: 155px; }

/* Anchors won't hide under sticky header */
a[id] { scroll-margin-top: 175px; }

/* Cards */
.card {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 18px;
  padding: 18px;
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
</style>
""",
        unsafe_allow_html=True,
    )


def render_sticky_header(name, role, contact_html, profile_img_b64=None):
    avatar_html = ""
    if profile_img_b64:
        avatar_html = f"<img class='avatar' src='data:image/jpeg;base64,{profile_img_b64}' />"

    # CRITICAL: start the string EXACTLY with <div...> (no leading newline/spaces)
    html = (
        f'<div class="sticky">'
        f'  <div class="header-row">'
        f'    <div class="id-row">'
        f'      {avatar_html}'
        f'      <div>'
        f'        <div style="font-size:34px;font-weight:900;color:gold;line-height:1;">{name}</div>'
        f'        <div style="font-size:26px;font-weight:900;color:limegreen;line-height:1.1;">{role}</div>'
        f'        <div class="muted" style="margin-top:6px;font-size:15px;">{contact_html}</div>'
        f'      </div>'
        f'    </div>'
        f'    <div class="nav">'
        f'      <a href="#summary">Summary</a>'
        #f'      <a href="#skills">Skills</a>'
        f'      <a href="#experience">Work Experience</a>'
        f'      <a href="#certs">Certifications</a>'
        f'      <a href="#publications">Publications</a>'
        f'      <a href="#projects">Projects</a>'
        f'      <a href="#education">Education</a>'
        f'      <a href="#about">About</a>'
        f'    </div>'
        f'  </div>'
        f'</div>'
        f'<div class="spacer"></div>'
    )

    st.markdown(html, unsafe_allow_html=True)


def section_anchor(anchor_id: str):
    st.markdown(f'<a id="{anchor_id}"></a>', unsafe_allow_html=True)


def card(title: str, body_html: str):
    st.markdown(
        f"""
<div class="card">
  <div style="font-size:20px;font-weight:800;margin-bottom:8px;">{title}</div>
  <div class="muted" style="font-size:15px;line-height:1.6;">{body_html}</div>
</div>
""",
        unsafe_allow_html=True,
    )


# ---------------------------
# Main app
# ---------------------------
def main():
    css()

    with st.sidebar:
        if st.button("🔄 Refresh / Clear cache"):
            st.cache_data.clear()
            st.rerun()

    token = None
    try:
        token = st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        token = None

    resume = load_resume_from_github(GITHUB_OWNER, GITHUB_REPO, RESUME_PATH_IN_REPO, BRANCH, token)

    profile_img_b64 = None
    if os.path.exists(PROFILE_IMG):
        with open(PROFILE_IMG, "rb") as img_file:
            profile_img_b64 = base64.b64encode(img_file.read()).decode()

    LINKEDIN_USER = "akhilaa2610"


    linkedin_url = f"https://www.linkedin.com/in/{LINKEDIN_USER}/"
    github_url = f"https://github.com/{GITHUB_OWNER}"
    contact_html = make_hyperlinked_contact(resume.get("contact_line", ""), linkedin_url, github_url)

    render_sticky_header(
        name=resume.get("name", "Akhila A"),
        role=resume.get("role", "Senior Data Engineer | Data Scientist"),
        contact_html=contact_html,
        profile_img_b64=profile_img_b64,
    )

    # SUMMARY
    section_anchor("summary")
    summary_text = (resume.get("summary", "") or "").strip()
    if summary_text:
        bullets = [s.strip() for s in re.split(r"(?<=[.!?])\s+", summary_text) if s.strip()]
        card("Professional Summary", "<br>".join([f"• {b}" for b in bullets]))
    else:
        card("Professional Summary", "No summary found in the resume.")

    # SKILLS
    #section_anchor("skills")
    #skills = resume.get("skills", {}) or {}
    #if isinstance(skills, dict) and skills:
    #   st.markdown(
    #       "<div class='card'><div style='font-size:20px;font-weight:800;margin-bottom:8px;'>Skills</div></div>",
    #        unsafe_allow_html=True,
    #    )
    #    for cat, val in skills.items():
    #        items = [x.strip() for x in re.split(r"[,\n]+", val) if x.strip()]
    #        chips = " ".join([f"<span class='chip'>{x}</span>" for x in items])
    #        st.markdown(
    #           f"<div class='card'><div style='font-weight:800;margin-bottom:8px;'>{cat}</div>{chips}</div>",
    #            unsafe_allow_html=True,
    #       )
    #else:
    #   card("Skills", "Could not read skills table from the DOCX.")

    # EXPERIENCE (logo-click)
    section_anchor("experience")
    exp = resume.get("experience", {}) or {}
    render_work_experience_clickable(exp, COMPANY_LOGOS)


    # PUBLICATIONS
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

    # ABOUT
    section_anchor("about")
    about_txt = download_raw_text(GITHUB_OWNER, GITHUB_REPO, "aboutpage.txt", BRANCH, token)
    if about_txt:
        card("About This Page", about_txt.replace("\n", "<br>"))
    else:
        card("About This Page", "aboutpage.txt not found in your GitHub repo root.")


if __name__ == "__main__":
    main()
