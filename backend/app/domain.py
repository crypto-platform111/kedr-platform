"""Version-dispatched strategy language. Schema 1 behavior remains frozen."""
from . import domain_v1, domain_v2

CATALOG = domain_v2.CATALOG
TIMEFRAMES = domain_v2.TIMEFRAMES
blank_strategy = domain_v2.blank_strategy
summarize_strategy = domain_v2.summarize_strategy


def node_catalog(schema_version=2):
    return domain_v1.node_catalog() if schema_version == 1 else domain_v2.node_catalog()


def templates():
    return domain_v1.templates()


def validate_strategy(spec, *, for_execution=True):
    if isinstance(spec, dict) and spec.get("schema_version") == 2:
        return domain_v2.validate_strategy(spec, for_execution=for_execution)
    return domain_v1.validate_strategy(spec)
