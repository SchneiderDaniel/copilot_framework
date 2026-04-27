from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml


@dataclass(slots=True)
class RegistryEntry:
    target_dir: str
    db_dir: str
    last_indexed_at: str | None = None


@dataclass(slots=True)
class RepoRegistry:
    version: int = 1
    default: str = "default"
    indexes: dict[str, RegistryEntry] = field(default_factory=dict)


class RegistryError(ValueError):
    """Raised when registry operations fail."""


def get_registry_path(cwd: Path | None = None) -> Path:
    root = cwd or Path.cwd()
    return root / ".cosk" / "registry.yaml"


def load_registry(cwd: Path | None = None) -> RepoRegistry:
    path = get_registry_path(cwd)
    if not path.exists():
        return RepoRegistry()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        indexes = {
            str(name): RegistryEntry(
                target_dir=str(entry["target_dir"]),
                db_dir=str(entry["db_dir"]),
                last_indexed_at=entry.get("last_indexed_at"),
            )
            for name, entry in (data.get("indexes", {}) or {}).items()
        }
        registry = RepoRegistry(version=int(data.get("version", 1)), default=str(data.get("default", "default")), indexes=indexes)
        return registry
    except Exception as exc:  # noqa: BLE001
        raise RegistryError(f"Invalid registry file at '{path}': {exc}") from exc


def save_registry(registry: RepoRegistry, cwd: Path | None = None) -> None:
    path = get_registry_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": registry.version,
        "default": registry.default,
        "indexes": {name: asdict(entry) for name, entry in sorted(registry.indexes.items())},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def upsert_index(
    name: str,
    target_dir: Path,
    db_dir: Path,
    *,
    last_indexed_at: str | None = None,
    cwd: Path | None = None,
) -> RepoRegistry:
    registry = load_registry(cwd)
    registry.indexes[name] = RegistryEntry(
        target_dir=target_dir.resolve().as_posix(),
        db_dir=db_dir.resolve().as_posix(),
        last_indexed_at=last_indexed_at,
    )
    if not registry.default:
        registry.default = name
    save_registry(registry, cwd)
    return registry


def remove_index(name: str, cwd: Path | None = None) -> RepoRegistry:
    registry = load_registry(cwd)
    if name not in registry.indexes:
        raise RegistryError(f"Unknown index_name '{name}'.")
    del registry.indexes[name]
    if registry.default == name:
        registry.default = sorted(registry.indexes)[0] if registry.indexes else "default"
    save_registry(registry, cwd)
    return registry


def set_default_index(name: str, cwd: Path | None = None) -> RepoRegistry:
    registry = load_registry(cwd)
    if name not in registry.indexes:
        raise RegistryError(f"Unknown index_name '{name}'.")
    registry.default = name
    save_registry(registry, cwd)
    return registry


def resolve_index(name: str | None = None, cwd: Path | None = None) -> tuple[str, RegistryEntry]:
    registry = load_registry(cwd)
    selected_name = name or registry.default
    if selected_name not in registry.indexes:
        raise RegistryError(f"Unknown index_name '{selected_name}'.")
    return selected_name, registry.indexes[selected_name]

