---
name: system-integrity-guard
description: Expert procedural guidance for cross-service impact analysis, security scanning, and SEO structural audits. Inspired by Snyk and LangGraph.
---

# Skill: System-Integrity-Guard (Mycroft)

Expert procedural guidance for cross-service impact analysis, security scanning, and SEO structural audits. Inspired by **Snyk** and **LangGraph**.

## Overview
This skill enables Mycroft to maintain architectural and security standards across the mono-repo.

## Core Procedures

### 1. Cross-Service Impact Analysis
- Map dependencies between Planhead (Dash/Flask), Hippocooking (JSON), and Myosotis (FastAPI) within the `flask_blogs/` directory.
- Audit Nginx gateway routing (`flask_blogs/nginx/`) for any breaking changes.
- Check `flask_blogs/docker-compose.yml` health and volume mount integrity.

### 2. Security Scan (Secrets & SAST)
- **Secrets Audit**: Scan all modified files for API keys, passwords, or `.env` exposure.
- **SAST (Static Analysis)**: Run `bandit` or `ruff` to identify common security vulnerabilities (e.g., SQLi, command injection).
- **Environment Audit**: Verify that production and development environment variables are isolated.

### 3. SEO & Structural Integrity
- Run **SEO-Optimizer** for every template change.
- Audit sitemap generation and `hreflang` tags.
- Verify meta-tag presence and OpenGraph consistency.

## Output Standard
- A "System Integrity Audit" in Myosotis (`technical_design`).
- Approved Technical Design with security/impact sign-off.
- Verified SEO scores and sitemap integrity.
