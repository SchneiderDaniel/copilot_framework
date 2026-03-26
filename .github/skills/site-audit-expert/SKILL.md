---
name: site-audit-expert
description: Expert procedural guidance for comprehensive route-by-route site audits using Chrome DevTools. Use when Gemini CLI needs to scan a website for console errors, network failures, and accessibility issues across all internal routes.
---

# Site Audit Expert

This skill provides a systematic workflow for auditing websites using the Chrome DevTools MCP. It ensures that no route is missed and that all types of errors (runtime, network, and accessibility) are captured.

## Workflow

### 1. Link Discovery (Crawl)
Start by identifying all internal routes from the homepage and key category pages. Use `mcp_chrome-devtools_evaluate_script` to extract all unique `<a>` tags pointing to the same domain.

```javascript
() => {
  const domain = window.location.hostname;
  const links = Array.from(document.querySelectorAll('a[href]'))
    .map(a => a.href)
    .filter(href => new URL(href).hostname === domain);
  return [...new Set(links)];
}
```

### 2. Systematic Audit (Batch Processing)
Organize the discovered routes into batches (e.g., 5-10 routes) to maintain context efficiency. For each route in a batch, perform the following:

1.  **Navigate**: Use `mcp_chrome-devtools_navigate_page`.
2.  **Capture Console**: Use `mcp_chrome-devtools_list_console_messages` to collect all errors, warnings, and logs.
3.  **Capture Network**: Use `mcp_chrome-devtools_list_network_requests` to identify any 4xx/5xx status codes or failed asset loads.
4.  **Capture Accessibility**: Use `mcp_chrome-devtools_take_snapshot` to identify missing labels, IDs, or other WCAG-related issues.

### 3. Reporting & Synthesis
Organize the findings into a structured Markdown table, categorizing them by:
- **Critical Errors**: Runtime exceptions (SyntaxError, ReferenceError) and 500s.
- **Broken Links**: 404s.
- **Accessibility Warnings**: Missing labels, ARIA issues, etc.
- **Debug Noise**: Verbose logs in production.

### 4. Integration
If requested, create or update a GitHub issue using `run_shell_command` with the `gh` CLI. Use a temporary file for the issue body to avoid shell escaping issues.

## Best Practices
- **Accept Cookies**: Always click "Accept" or "Akzeptieren" on the first page to clear overlays that might interfere with audits.
- **Language Variants**: If the site supports multiple languages (e.g., `?lang=en`), audit a representative sample of tools in each language.
- **Wait for Load**: Ensure the page has fully loaded (or wait for specific elements) before capturing console or network data.
- **Deduplicate Findings**: If multiple pages share the same error (e.g., a broken global footer script), group them in the report.

## Tools
- `mcp_chrome-devtools_*`: Core auditing tools.
- `gh issue create/edit`: Integration with GitHub.
