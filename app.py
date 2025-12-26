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
    "This is my interactive portfolio built with Streamlit. "
    "It showcases my projects and experience using live GitHub data."
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
