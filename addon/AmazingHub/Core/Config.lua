----------------------------------------------------------------------
-- Amazing Hub - Configuration
-- Single source of truth for all addon-wide constants.
-- This file is loaded first (before Core.lua) so every module can
-- safely reference AmazingHub.* constants from the start.
----------------------------------------------------------------------

-- Create the primary namespace. Using "or {}" is idempotent — safe to
-- call even if a future loader has already created the table.
--
_G.AmazingHub = _G.AmazingHub or {}

-- ── Product identity ─────────────────────────────────────────────
AmazingHub.ADDON_NAME        = "Amazing Hub"
AmazingHub.NAMESPACE         = "AmazingHub"

-- ── Version ───────────────────────────────────────────────────────
AmazingHub.VERSION           = "0.5.4"  -- kept in sync with AmazingHub.toc by the release workflow
AmazingHub.COMM_VERSION      = 1

-- ── SavedVariables ────────────────────────────────────────────────
AmazingHub.DB_GLOBAL         = "AmazingHubDB"

-- ── Communication prefixes ────────────────────────────────────────
AmazingHub.PREFIX            = "AMAZINGHUB"

-- ── Slash commands ────────────────────────────────────────────────
AmazingHub.SLASH_PRIMARY     = "/amazing"
