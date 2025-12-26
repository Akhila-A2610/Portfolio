import json
import requests
import streamlit as st

st.set_page_config(page_title="Portfolio", layout="wide")

# Load resume data
with open("resume_data.json", "r", encoding="utf-8") as f:
    resume = json.load(f)

st.title(f"👋 Hi, I'm {resume['name']}")
st.write(resume["title"])

st.divider()

# About
st.header("About")
st.write(
    "This page is part of my interactive portfolio and resume, built using Streamlit. It automatically pulls information from my GitHub repositories so that the projects and experience shown here stay current as I continue to grow and update my work."

"The focus of this website is simplicity and clarity, making it easy to explore my work while keeping the codebase clean and easy to maintain. The source code for this project is available and can be shared upon request. The application is primarily developed using Python and Streamlit for the core logic and interface, with REST APIs and requests used to retrieve live data from GitHub, and HTML and CSS applied for custom styling and layout."
)

st.divider()

# GitHub Projects
st.header("Projects")

username = resume["github_username"]
url = f"https://api.github.com/users/{username}/repos?sort=updated"

repos = requests.get(url).json()

for repo in repos:
    if repo["fork"]:
        continue
    st.subheader(repo["name"])
    st.write(repo["description"])
    st.write(repo["html_url"])
    st.divider()
