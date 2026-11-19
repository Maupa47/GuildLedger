std = "lua51"
max_line_length = 120
exclude_files = { "vendor-ref/**", "addon/AmazingHub/**" }   -- the hub is GuildOS's code, checked by its own tests

-- Globals the addons may write.
globals = { "GuildLedgerDB", "GuildLedgerAPI", "SlashCmdList", "SLASH_GUILDLEDGER1", "SLASH_GUILDLEDGER2" }

-- Client globals that are read. Every one must be documented for 1.60.1 (CLAUDE.md 10.1).
read_globals = {
    "C_Club", "C_ChatInfo", "C_GuildInfo", "C_Timer", "Enum",
    "CreateFrame", "DEFAULT_CHAT_FRAME", "GetServerTime", "GetTime",
    "GetNumGuildMembers", "GetGuildRosterInfo", "QueryGuildEventLog", "GetNumGuildEvents", "GetGuildEventInfo",
    "issecretvalue", "ReloadUI", "debugprofilestop", "date", "time", "UnitName",
    "C_Map", "IsInInstance", "UnitInParty", "UnitInRaid", "RAID_CLASS_COLORS", "WorldMapFrame", "GameTooltip", "GameFontHighlightSmall",
    "ERR_GUILD_JOIN_S", "ERR_GUILD_LEAVE_S", "ERR_GUILD_REMOVE_SS", "ERR_GUILD_PROMOTE_SSS", "ERR_GUILD_DEMOTE_SSS",
}
