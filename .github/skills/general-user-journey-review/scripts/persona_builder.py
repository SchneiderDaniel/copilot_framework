#!/usr/bin/env python3
"""
persona_builder.py — Scans a project and synthesizes realistic user personas.

Usage:
    python persona_builder.py --project-path <path> [--output personas.json]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


PERSONA_TEMPLATE = {
    "id": "",
    "name": "",
    "role": "",
    "technical_level": "",   # novice | intermediate | expert
    "goals": [],
    "frustrations": [],
    "context": "",
    "device": "",
    "apple_ux_bar": "",      # expects_zero_docs | expects_minimal_docs | ok_with_docs
}


def scan_readme(project_path: Path) -> str:
    for name in ["README.md", "readme.md", "README.rst", "README.txt"]:
        p = project_path / name
        if p.exists():
            return p.read_text(encoding="utf-8", errors="ignore")[:5000]
    return ""


def scan_docs(project_path: Path) -> str:
    texts = []
    for pattern in ["docs/**/*.md", "doc/**/*.md", "documentation/**/*.md"]:
        for p in sorted(project_path.glob(pattern))[:5]:
            texts.append(p.read_text(encoding="utf-8", errors="ignore")[:800])
    return "\n".join(texts)


def scan_package_meta(project_path: Path) -> str:
    candidates = [
        "package.json", "pyproject.toml", "setup.py", "setup.cfg",
        "Cargo.toml", "go.mod",
    ]
    for name in candidates:
        p = project_path / name
        if p.exists():
            return p.read_text(encoding="utf-8", errors="ignore")[:1000]
    return ""


def scan_cli_help(project_path: Path) -> str:
    """Try to get --help output from common entry points."""
    outputs = []
    entry_points = ["main.py", "cli.py", "run.py", "app.py", "__main__.py"]
    for ep in entry_points:
        for p in sorted(project_path.rglob(ep))[:3]:
            try:
                result = subprocess.run(
                    [sys.executable, str(p), "--help"],
                    capture_output=True, text=True, timeout=5, cwd=str(project_path)
                )
                if result.stdout and len(result.stdout) > 20:
                    outputs.append(f"# {p.name} --help\n{result.stdout[:600]}")
            except Exception:
                pass
    # Also try npx-style scripts listed in package.json
    pkg = project_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            if scripts:
                outputs.append(f"# npm scripts: {list(scripts.keys())}")
        except Exception:
            pass
    return "\n".join(outputs)


def detect_app_type(project_path: Path, text: str) -> str:
    text_lower = text.lower()
    scores = {
        "web_app": sum(1 for k in ["flask", "django", "fastapi", "express", "react", "vue",
                                    "web app", "webapp", "browser", "html", "css"] if k in text_lower),
        "cli_tool": sum(1 for k in ["cli", "command line", "terminal", "npx", "argparse",
                                     "click", "typer", "subprocess"] if k in text_lower),
        "api": sum(1 for k in ["api", "rest", "graphql", "endpoint", "swagger",
                                "openapi", "http"] if k in text_lower),
        "library": sum(1 for k in ["library", "package", "module", "import",
                                    "pip install", "npm install"] if k in text_lower),
    }
    detected = max(scores, key=lambda k: scores[k])
    # Docker is a strong signal for web_app / service
    if (project_path / "docker-compose.yml").exists() or (project_path / "Dockerfile").exists():
        if scores["web_app"] >= scores["cli_tool"]:
            return "web_app"
    return detected if scores[detected] > 0 else "unknown"


def detect_urls(project_path: Path) -> list[str]:
    """Find any localhost URLs in config files."""
    urls = []
    for pattern in ["*.yml", "*.yaml", "*.env", "*.conf", "*.cfg", "*.toml"]:
        for p in sorted(project_path.glob(pattern))[:10]:
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                found = re.findall(r'https?://(?:localhost|127\.0\.0\.1)[:\w/.-]*', content)
                urls.extend(found)
            except Exception:
                pass
    return list(set(urls))[:5]


def extract_features(text: str) -> list[str]:
    features = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r'^[-*•✓✅]\s+\w', line):
            clean = re.sub(r'^[-*•✓✅]\s+', '', line).strip()
            if 5 < len(clean) < 120:
                features.append(clean)
    return features[:12]


def build_personas(app_type: str, features: list[str], readme: str) -> list[dict]:
    readme_lower = readme.lower()
    personas = []

    # --- Persona 1: First-time user / newcomer ---
    p1 = {**PERSONA_TEMPLATE}
    p1["id"] = "persona-01-newcomer"
    p1["name"] = "Alex (First-time User)"
    p1["role"] = "Someone discovering this product for the first time"
    p1["technical_level"] = "novice" if app_type in ("web_app", "cli_tool") else "intermediate"
    p1["goals"] = [
        "Understand what this product does within 30 seconds",
        "Complete the core task without reading any documentation",
        "Get a result they can show or use immediately",
    ]
    p1["frustrations"] = [
        "Jargon or technical terms with no explanation",
        "More than 3 steps before seeing any value",
        "Errors that don't explain how to fix them",
        "Having to read docs before starting",
    ]
    p1["context"] = (
        "Heard about this via a recommendation or search. "
        "Opens it for the first time with no prior context."
    )
    p1["device"] = "MacBook, Chrome browser" if app_type == "web_app" else "MacBook, Terminal"
    p1["apple_ux_bar"] = "expects_zero_docs"
    personas.append(p1)

    # --- Persona 2: Regular / returning user ---
    p2 = {**PERSONA_TEMPLATE}
    p2["id"] = "persona-02-regular"
    p2["name"] = "Sam (Regular User)"
    p2["role"] = "Person who uses this product regularly as part of their workflow"
    p2["technical_level"] = "intermediate"
    p2["goals"] = [
        "Complete recurring tasks quickly and efficiently",
        "Not waste time on repetitive setup steps",
        "Discover advanced features naturally",
    ]
    p2["frustrations"] = [
        "Extra clicks for frequent actions (no shortcuts)",
        "Inconsistent behavior between sessions",
        "Slow feedback — waiting without knowing what's happening",
        "Features that worked last time now behave differently",
    ]
    p2["context"] = "Uses this product several times a week. Knows the basics, wants efficiency."
    p2["device"] = "MacBook or Windows, Chrome" if app_type == "web_app" else "Any OS, Terminal"
    p2["apple_ux_bar"] = "expects_minimal_docs"
    personas.append(p2)

    # --- Persona 3: Power user / expert (only for advanced products) ---
    is_advanced = any(k in readme_lower for k in [
        "advanced", "config", "api key", "plugin", "extension",
        "integration", "script", "automate", "pipeline", "cli",
    ])
    if is_advanced:
        p3 = {**PERSONA_TEMPLATE}
        p3["id"] = "persona-03-poweruser"
        p3["name"] = "Jordan (Power User)"
        p3["role"] = "Technical user integrating this into larger systems or pipelines"
        p3["technical_level"] = "expert"
        p3["goals"] = [
            "Automate and script interactions without manual steps",
            "Integrate with other tools via API or config",
            "Understand all configuration options",
        ]
        p3["frustrations"] = [
            "No CLI or API access for automation",
            "Black-box behavior with no observability",
            "Can't configure without modifying source code",
        ]
        p3["context"] = (
            "Uses this as part of a larger pipeline. "
            "Cares about reliability, scriptability, and transparency."
        )
        p3["device"] = "Any OS, Terminal / API client"
        p3["apple_ux_bar"] = "ok_with_docs"
        personas.append(p3)

    return personas


def main():
    parser = argparse.ArgumentParser(
        description="Scan a project and generate user personas for a UX journey review."
    )
    parser.add_argument("--project-path", default=".", help="Root path of the project to analyze")
    parser.add_argument("--output", default=None, help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    project_path = Path(args.project_path).resolve()
    print(f"[persona_builder] Scanning: {project_path}", file=sys.stderr)

    readme = scan_readme(project_path)
    docs = scan_docs(project_path)
    cli_help = scan_cli_help(project_path)
    meta = scan_package_meta(project_path)
    urls = detect_urls(project_path)
    combined = f"{readme}\n{docs}\n{cli_help}\n{meta}"

    app_type = detect_app_type(project_path, combined)
    features = extract_features(combined)
    personas = build_personas(app_type, features, combined)

    result = {
        "project_path": str(project_path),
        "app_type": app_type,
        "detected_features": features,
        "detected_urls": urls,
        "personas": personas,
    }

    output = json.dumps(result, indent=2)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"[persona_builder] Written {len(personas)} personas to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
