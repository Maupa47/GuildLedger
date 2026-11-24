-- Amazing Hub developer features (docs/addon/HUB_AUDIT.md 10.2, decision 7 of 2026-11-24).
-- Amazing Hub loads after this addon (its TOC lists AmazingHubDev under OptionalDeps). Wherever one of its tools
-- that act for the player starts, it checks this global (tools/rebrand-hub.py, patch section 8); without this
-- addon those tools stay hidden. tools/install.ps1 links this folder into the AddOns folder;
-- tools/package-collector.ps1 never packs it.
AmazingHubDevFeatures = true
