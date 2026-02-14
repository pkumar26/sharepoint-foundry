"""Dry-run smoke test: imports, config, and server startup."""

import sys

print(f"Python: {sys.version}")
print()

# ── Test imports ──────────────────────────────────────────────────────────
print("Testing imports...")
errors = []

try:
    from src.config import get_settings
    print("  config OK")
except Exception as e:
    print(f"  config FAIL: {e}")
    errors.append(("config", e))

try:
    from src.services.search import SearchBackend, IndexerSearchService
    print("  search OK")
except Exception as e:
    print(f"  search FAIL: {e}")
    errors.append(("search", e))

try:
    from src.services.kb_search import KnowledgeBaseSearchService
    print("  kb_search OK")
except Exception as e:
    print(f"  kb_search FAIL: {e}")
    errors.append(("kb_search", e))

try:
    from src.services.auth import AuthService
    print("  auth OK")
except Exception as e:
    print(f"  auth FAIL: {e}")
    errors.append(("auth", e))

try:
    from src.agents.sharepoint_qa import SharePointQAAgent
    print("  agent OK")
except Exception as e:
    print(f"  agent FAIL: {e}")
    errors.append(("agent", e))

try:
    from src.main import app
    print("  main OK")
except Exception as e:
    print(f"  main FAIL: {e}")
    errors.append(("main", e))

# ── Test config ───────────────────────────────────────────────────────────
print()
print("Settings:")
try:
    s = get_settings()
    print(f"  search_approach:      {s.search_approach}")
    print(f"  knowledge_base_name:  {s.knowledge_base_name}")
    print(f"  knowledge_source_name:{s.knowledge_source_name}")
    print(f"  azure_search_endpoint:{s.azure_search_endpoint}")
    print(f"  azure_search_api_key: {s.azure_search_api_key[:8]}...")
except Exception as e:
    print(f"  Settings FAIL: {e}")
    errors.append(("settings", e))

# ── Test KB search service instantiation ──────────────────────────────────
print()
print("Backend instantiation:")
try:
    s = get_settings()
    if s.search_approach == "indexer":
        print("  Approach 1 (indexer) — skipping (needs Azure credential)")
    else:
        svc = KnowledgeBaseSearchService(
            endpoint=s.azure_search_endpoint,
            api_version=s.azure_search_api_version,
            knowledge_base_name=s.knowledge_base_name,
            knowledge_source_name=s.knowledge_source_name,
            approach=s.search_approach,
            api_key=s.azure_search_api_key,
        )
        print(f"  KnowledgeBaseSearchService OK (kind={svc._kind})")
except Exception as e:
    print(f"  Backend FAIL: {e}")
    errors.append(("backend", e))

# ── Summary ───────────────────────────────────────────────────────────────
print()
if errors:
    print(f"FAILED: {len(errors)} error(s)")
    for name, err in errors:
        print(f"  {name}: {err}")
    sys.exit(1)
else:
    print("All checks passed!")
    sys.exit(0)
