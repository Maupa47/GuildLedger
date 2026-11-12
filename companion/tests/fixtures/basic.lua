
GuildLedgerDB = {
["schema"] = 1,
["meta"] = {
["addon"] = "0.1.0",
["writer"] = "Testa Collector",
["saved"] = 1794430000,
},
["guilds"] = {
["100200300"] = {
["name"] = "Synthetic Guild",
["chat"] = {
{
["id"] = "1794420000100000:1000",
["t"] = 1794420000,
["s"] = "g",
["a"] = "Alia Testwood",
["g"] = "Player-1111-0000AAAA",
["m"] = "hello guild",
["fd"] = false,
["ed"] = false,
["del"] = false,
["src"] = "live",
}, -- [1]
{
["id"] = "1794420010200000:1001",
["t"] = 1794420010,
["s"] = "g",
["a"] = "Bram Exampleson",
["g"] = "Player-1111-0000BBBB",
["m"] = "anyone got |cff0070dd|Hitem:2140::::::::20:::::|h[Carving Knife]|h|r?",
["fd"] = false,
["ed"] = true,
["del"] = false,
["src"] = "live",
}, -- [2]
{
["id"] = "1794420020300000:1002",
["t"] = 1794420020,
["s"] = "g",
["a"] = "Cora Sample",
["g"] = "Player-1111-0000CCCC",
["fd"] = false,
["ed"] = false,
["del"] = false,
["src"] = "meta",
}, -- [3]
{
["id"] = "ev|1794420021|Cora Sample|1a2b3c4d",
["t"] = 1794420021,
["s"] = "g",
["a"] = "Cora Sample",
["g"] = "Player-1111-0000CCCC",
["m"] = "this line lost its club partner",
["fd"] = false,
["ed"] = false,
["del"] = false,
["src"] = "event",
}, -- [4]
{
["id"] = "1794420030400000:1003",
["t"] = 1794420030,
["s"] = "o",
["a"] = "Alia Testwood",
["g"] = "Player-1111-0000AAAA",
["m"] = "officer note: @everyone check bank",
["fd"] = false,
["ed"] = false,
["del"] = false,
["src"] = "live",
}, -- [5]
{
["id"] = "1794420040500000:1004",
["t"] = 1794420040,
["s"] = "g",
["a"] = "DiscordUser",
["m"] = "hi from discord",
["fd"] = true,
["ed"] = false,
["del"] = false,
["src"] = "live",
}, -- [6]
{
["id"] = "1794420050600000:1005",
["t"] = 1794420050,
["s"] = "g",
["a"] = "Bram Exampleson",
["g"] = "Player-1111-0000BBBB",
["fd"] = false,
["ed"] = false,
["del"] = true,
["src"] = "meta",
}, -- [7]
},
["cursor"] = {
["g"] = "1794420050600000:1005",
["o"] = "1794420030400000:1003",
},
["roster"] = {
["Player-1111-0000AAAA"] = {
["n"] = "Alia Testwood",
["r"] = 1,
["rn"] = "Officer",
["l"] = 40,
["c"] = "MAGE",
["fs"] = 1794000000,
["ls"] = 1794420000,
},
["Player-1111-0000BBBB"] = {
["n"] = "Bram Exampleson",
["r"] = 5,
["rn"] = "Member",
["l"] = 22,
["c"] = "WARRIOR",
["fs"] = 1794100000,
["ls"] = 1794420050,
},
["Player-1111-0000CCCC"] = {
["n"] = "Cora Sample",
["r"] = 6,
["rn"] = "Social",
["l"] = 12,
["c"] = "PRIEST",
["fs"] = 1794410000,
["ls"] = 1794420021,
},
},
["rosterAt"] = 1794420060,
["ev"] = {
{
["id"] = "join|Cora Sample||358882000",
["t"] = 1794410000,
["p"] = true,
["k"] = "join",
["n"] = "Cora Sample",
["g"] = "Player-1111-0000CCCC",
["src"] = "sys",
}, -- [1]
{
["id"] = "leave|Dax Gone||diff:498450",
["t"] = 1794420060,
["p"] = false,
["k"] = "leave",
["n"] = "Dax Gone",
["g"] = "Player-1111-0000DDDD",
["src"] = "diff",
}, -- [2]
{
["id"] = "leave|Dax Gone||log:498447",
["t"] = 1794409200,
["p"] = false,
["k"] = "leave",
["n"] = "Dax Gone",
["src"] = "log",
}, -- [3]
{
["id"] = "kick|Eli Rowdy|Alia Testwood|358884010",
["t"] = 1794420050,
["p"] = true,
["k"] = "kick",
["n"] = "Eli Rowdy",
["by"] = "Alia Testwood",
["src"] = "sys",
}, -- [4]
{
["id"] = "promote|Bram Exampleson|Alia Testwood|358884011",
["t"] = 1794420055,
["p"] = true,
["k"] = "promote",
["n"] = "Bram Exampleson",
["by"] = "Alia Testwood",
["d"] = "Member",
["src"] = "sys",
}, -- [5]
},
},
},
}
