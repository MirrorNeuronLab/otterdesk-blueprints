from __future__ import annotations

from .catalog_loader import load_blueprint_index_products, load_renamed_blueprints


RENAMED_BLUEPRINTS = load_renamed_blueprints()
LEGACY_ALIASES = {old: new for old, (new, _reason) in RENAMED_BLUEPRINTS.items()}
PRODUCT_PROFILES = load_blueprint_index_products()
