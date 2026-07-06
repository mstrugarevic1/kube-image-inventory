import httpx
import logging
from typing import List, Optional
from packaging import version
from .models import RegistryCache
from .db import SessionLocal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

async def get_latest_tag(repository: str) -> Optional[str]:
    # Check cache first
    db = SessionLocal()
    cache = db.query(RegistryCache).filter_by(image_repository=repository).first()
    if cache and cache.last_updated > datetime.utcnow() - timedelta(hours=6):
        db.close()
        return cache.latest_tag
    db.close()

    tags = []
    if "ghcr.io" in repository:
        tags = await _fetch_ghcr_tags(repository)
    elif "/" not in repository or "docker.io" in repository:
        tags = await _fetch_dockerhub_tags(repository)
    
    if not tags:
        return None

    # Filter for semver-like tags
    semver_tags = []
    for t in tags:
        try:
            v = version.parse(t)
            if not v.is_prerelease:
                semver_tags.append((v, t))
        except Exception:
            continue
    
    if not semver_tags:
        return None

    semver_tags.sort(key=lambda x: x[0], reverse=True)
    latest = semver_tags[0][1]

    # Update cache
    db = SessionLocal()
    if cache:
        cache.latest_tag = latest
        cache.tags_json = tags
        cache.last_updated = datetime.utcnow()
    else:
        new_cache = RegistryCache(
            image_repository=repository,
            latest_tag=latest,
            tags_json=tags
        )
        db.add(new_cache)
    db.commit()
    db.close()

    return latest

async def _fetch_dockerhub_tags(repository: str) -> List[str]:
    if "docker.io/" in repository:
        repository = repository.replace("docker.io/", "")
    if "/" not in repository:
        repository = f"library/{repository}"
    
    url = f"https://registry.hub.docker.com/v2/repositories/{repository}/tags?page_size=100"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return [t["name"] for t in data.get("results", [])]
    except Exception as e:
        logger.error(f"Failed to fetch Docker Hub tags for {repository}: {e}")
    return []

async def _fetch_ghcr_tags(repository: str) -> List[str]:
    # GHCR often requires auth for listing tags even for public repos if not using the right API
    # For MVP, we'll try a simple approach or note the limitation.
    # Public GHCR tags can be fetched via: https://ghcr.io/v2/OWNER/IMAGE/tags/list
    # But it requires a token even for public repos.
    repo_path = repository.replace("ghcr.io/", "")
    token_url = f"https://ghcr.io/token?scope=repository:{repo_path}:pull"
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.get(token_url)
            if token_resp.status_code == 200:
                token = token_resp.json().get("token")
                list_url = f"https://ghcr.io/v2/{repo_path}/tags/list"
                list_resp = await client.get(list_url, headers={"Authorization": f"Bearer {token}"})
                if list_resp.status_code == 200:
                    return list_resp.json().get("tags", [])
    except Exception as e:
        logger.error(f"Failed to fetch GHCR tags for {repository}: {e}")
    return []

def compare_tags(current: str, latest: str) -> str:
    if current == latest:
        return "current"
    try:
        if version.parse(current) < version.parse(latest):
            return "outdated"
    except Exception:
        pass
    return "unknown"
