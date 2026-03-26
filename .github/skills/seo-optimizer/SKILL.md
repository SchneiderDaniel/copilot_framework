---
name: seo-optimizer
description: Audit and optimize PlAnhead templates for SEO, GEO, and pSEO. Checks for meta tags, Schema.org JSON-LD (FAQPage, WebApplication, FinancialProduct), and related tools.
---

# SEO Optimizer Skill

This skill ensures that all pages in PlAnhead are optimized for search engines (SEO), AI agents (GEO), and programmatic discovery (pSEO).

## Core Optimization Components

Every calculator/tool template should include:

1.  **Meta Blocks**:
    - `title`: Unique and keyword-rich.
    - `meta_description`: Compelling summary (approx. 150-160 chars).
    - `keywords`: Relevant terms.

2.  **Structured Data (`structured_data` block)**:
    - `WebApplication` or `FinancialProduct` schema.
    - `BreadcrumbList` (automatically handled by `base.html`, can be extended).
    - **No Duplicate FAQ Schema**: NEVER define `FAQPage` manually if using the `faq_section` macro.

3.  **UI Macros (via `macros.html`)**:
    - `faq_section`: Handles both UI accordion and `FAQPage` JSON-LD.
    - `citable_facts`: Mandatory for GEO; provides verified facts and links to `/facts.json`.
    - `render_related_tools`: Internal linking for crawlability.

4.  **Generative Engine Optimization (GEO)**:
    - Aggressive Schema.org markup.
    - Citable facts via the `citable_facts` macro.
    - Machine-readable data at `/facts.json`.

5.  **pSEO Registry (`app/data/tools.py`)**:
    - Every tool MUST have `blog_title` and `blog_description_seo`.
    - `faq` and `verified_claims` should be provided in the registry for dynamic blog generation.

## Standards & Security
- **JSON-LD**: Always use `|tojson|safe` for dynamic variables in script blocks to prevent injection and syntax errors.
- **Robot Control**: Specialized templates (PDF exports, internal tools) MUST include `<meta name="robots" content="noindex, nofollow">`.
- **Localization**: All meta tags and schema descriptions must be wrapped in `_()` for translation.

## Usage

### 1. Run Audit
Use the audit script to identify pages missing optimizations:
```bash
python .gemini/skills/seo-optimizer/scripts/seo_audit.py
```

### 2. Apply Optimizations
When implementing a new tool:
- Import macros: `{% from "macros.html" import faq_section, render_related_tools, citable_facts %}`
- Define `faq_items` (or use registry data).
- Define `verified_facts`.
- Call macros at the bottom of the content block.
