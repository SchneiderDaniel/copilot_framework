import os
import re
import sys

# Configuration
TEMPLATE_DIR = "flask_blogs/flask_planhead/app/templates"
TOOLS_FILE = "flask_blogs/flask_planhead/app/data/tools.py"
EXCLUDE_FILES = [
    "base.html", "macros.html", "robots.txt", "sitemap_template.xml", 
    "legal_disclosure.html", "privacy_policy.html", "cookie_policy.html", 
    "feedback.html"
]

def audit_templates():
    results = []
    
    # 1. Load TOOLS registry
    tools_content = ""
    if os.path.exists(TOOLS_FILE):
        with open(TOOLS_FILE, "r", encoding="utf-8") as tf:
            tools_content = tf.read()

    # 2. Walk through templates
    for root, dirs, files in os.walk(TEMPLATE_DIR):
        for file in files:
            # Only audit .html files
            if not file.endswith(".html"):
                continue
                
            # Skip excluded files
            if file in EXCLUDE_FILES:
                continue

            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, TEMPLATE_DIR).replace("\\", "/")
            
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Identify special templates
            is_pdf = "pdf_export" in file
            is_blog_post = "blog/post.html" in rel_path
            
            # Check if file is registered as a tool
            is_tool = rel_path in tools_content
            
            missing = []
            
            # ROBOTS CHECK
            if is_pdf:
                if 'name="robots" content="noindex' not in content:
                    missing.append("robots noindex (Required for PDFs)")
                # Skip other checks for PDFs
                if missing:
                    results.append({"file": rel_path, "missing": missing})
                continue

            # BASIC SEO CHECK
            if "{% block title %}" not in content: missing.append("block title")
            if "{% block meta_description %}" not in content: missing.append("block meta_description")
            if "{% block keywords %}" not in content: missing.append("block keywords")
            
            # MACRO CHECKS
            has_faq_macro = "faq_section(" in content
            has_faq_macro_schema = has_faq_macro and "include_schema=false" not in content
            has_faq_manual_schema = '"@type": "FAQPage"' in content
            
            if has_faq_macro_schema and has_faq_manual_schema:
                missing.append("DUPLICATE FAQPage Schema (Macro + Manual detected)")
            
            # TOOL SPECIFIC CHECKS
            if is_tool:
                if "citable_facts(" not in content: missing.append("citable_facts macro (GEO)")
                if "render_related_tools(" not in content: missing.append("render_related_tools macro")
                if '"@type": "WebApplication"' not in content and '"@type": "FinancialProduct"' not in content:
                    missing.append("WebApplication/FinancialProduct schema (GEO)")
            
            # BLOG SPECIFIC CHECKS
            if is_blog_post:
                if '"@type": "BlogPosting"' not in content: missing.append("BlogPosting schema")

            if missing:
                results.append({
                    "file": rel_path,
                    "missing": missing
                })

    # 3. Registry Audit (Split-based parsing)
    registry_issues = []
    if tools_content:
        # Split by "id": to get rough blocks
        parts = tools_content.split('"id":')
        for part in parts[1:]: # Skip preamble
            # Extract id
            id_match = re.search(r'^\s*"(.+?)"', part)
            if not id_match: continue
            tid = id_match.group(1)
            
            # Take only until the end of this dict item (rough approximation)
            # We look for the next "id": or the end of the list
            block = part.split('"id":')[0]
            
            if '"blog_title":' not in block: registry_issues.append(f"Tool '{tid}': Missing blog_title")
            if '"blog_description_seo":' not in block: registry_issues.append(f"Tool '{tid}': Missing blog_description_seo")
            if '"faq":' not in block: registry_issues.append(f"Tool '{tid}': Missing faq entries")
            if '"verified_claims":' not in block: registry_issues.append(f"Tool '{tid}': Missing verified_claims")

    # 4. Print Summary
    print("\n" + "="*60)
    print("🔍 PLAnhead SEO/GEO Audit Report")
    print("="*60)
    
    if not results and not registry_issues:
        print("✅ SUCCESS: All templates and registry entries follow SEO standards.")
    else:
        if results:
            print(f"\n📊 Template Issues ({len(results)} files):")
            for res in results:
                print(f"  • {res['file']}")
                for m in res['missing']:
                    print(f"    - {m}")
        
        if registry_issues:
            print(f"\n🗃️ Registry Issues (tools.py):")
            for issue in registry_issues:
                print(f"  • {issue}")

    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    if not os.path.exists(TEMPLATE_DIR):
        print(f"Error: Template directory '{TEMPLATE_DIR}' not found.")
        sys.exit(1)
    audit_templates()
