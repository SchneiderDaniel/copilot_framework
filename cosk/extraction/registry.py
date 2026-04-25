from __future__ import annotations

from cosk.config import CoskConfig, LanguageSettings


def build_extension_registry(config: CoskConfig) -> dict[str, LanguageSettings]:
    registry: dict[str, LanguageSettings] = {}
    for language in config.extraction.supported_languages:
        if not language.enabled:
            continue
        for extension in language.extensions:
            if extension in registry:
                raise ValueError(f"Duplicate extension mapping found for {extension!r}")
            registry[extension] = language
    return registry
