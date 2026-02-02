# genro-proxy

Base proxy package for Genro microservices.

## Overview

`genro-proxy` provides common infrastructure for building Genro-based microservices:

- **SQL Layer** - Database abstraction with SqlDb, Table, Column, and adapters (SQLite, PostgreSQL)
- **Storage Layer** - File storage with StorageManager and StorageNode (local filesystem + cloud: S3, GCS, Azure)
- **Tools** - Utilities for encryption, HTTP client, Prometheus metrics, REPL
- **Interface** - Base classes for FastAPI apps (ApiBase), CLI (CliBase), and REST endpoints (EndpointBase)
- **Entities** - Base tables for instance, tenant, account, storage, and command_log
- **ProxyBase** - Foundation class for building domain-specific proxies

## Installation

```bash
pip install genro-proxy
```

### Optional Dependencies

```bash
# PostgreSQL support
pip install genro-proxy[postgresql]

# Cloud storage (S3, GCS, Azure)
pip install genro-proxy[cloud]

# All extras
pip install genro-proxy[all]
```

## Usage

```python
from proxy import ProxyBase, ProxyConfigBase

class MyProxy(ProxyBase):
    """Custom proxy extending the base."""

    def __init__(self, config: ProxyConfigBase):
        super().__init__(config)
        # Add custom initialization

# Create and run
config = ProxyConfigBase(db_path="my_service.db", instance_name="my-proxy")
proxy = MyProxy(config)
await proxy.init()
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete architecture plan.

## Projects Using genro-proxy

- [genro-mail-proxy](https://github.com/genropy/genro-mail-proxy) - Email dispatcher microservice
- [genro-wopi](https://github.com/genropy/genro-wopi) - WOPI server for Office integration

## License

Apache License 2.0 - See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read the contribution guidelines in the main [meta-genro-modules](https://github.com/softwellsrl/meta-genro-modules) repository.
