# Claude Code Instructions - genro-proxy

**Parent Document**: This project follows all policies from the central [meta-genro-modules CLAUDE.md](https://github.com/softwellsrl/meta-genro-modules/blob/main/CLAUDE.md)

## Project-Specific Context

### Current Status
- Development Status: Pre-Alpha
- Has Implementation: No (architecture phase)

### Project Description
Base proxy package for Genro microservices. Provides common infrastructure:
- SQL layer (SqlDb, Table, Column, adapters)
- Storage layer (StorageManager, StorageNode with local + cloud support)
- Tools (encryption, http_client, prometheus, repl)
- Interface (ApiBase, CliBase, EndpointBase)
- Base entities (instance, tenant, account, storage, command_log)
- ProxyBase class for building domain-specific proxies

### Architecture Document
See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete architecture plan.

---

## Special Commands

### "mostra righe" / "mostra le righe" / "rimetti qui le righe" (show lines)

When the user asks to show code lines:

1. Show **only** the requested code snippet with some context lines
2. Number the lines
3. **DO NOT** add considerations, evaluations, or explanations
4. Copy the code directly into the chat

---

## Critical Safety Rules

### NEVER Remove or Move Files Without Explicit Consent

**RULE**: MAI MAI MAI rimuovere cartelle, spostare documenti o fare `rm -rf` senza consenso esplicito dell'utente.

Prima di qualsiasi operazione distruttiva:
1. **FERMARSI** e chiedere conferma esplicita
2. **ELENCARE** esattamente cosa verrà rimosso/spostato
3. **ASPETTARE** un "sì" o "ok" esplicito

Questo include:
- `rm`, `rm -rf`, `rm -r`
- `mv` di cartelle
- `git clean`
- Qualsiasi comando che elimina o sposta file/cartelle

**NON FARE MAI** assunzioni tipo "sistemo tutto" o "ripristino lo stato originale" che comportano eliminazioni.

---

**All general policies are inherited from the parent document.**
