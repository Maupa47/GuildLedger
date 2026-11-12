
TrickyDB = {
["quote"] = "she said \"hi\"",
["backslash"] = "C:\\Games\\WoW",
["newline"] = "line1\nline2",
["decimal"] = "M\195\164dchen",
["raw_utf8"] = "Testmagø 🙂",
["brackets"] = "not a long string ]] [[ nope",
["link"] = "|cffa335ee|Hitem:19019::::::::60:::::|h[Thunderfury, Blessed Blade of the Windseeker]|h|r",
["single"] = 'single \'quoted\'',
["tab"] = "a\tb",
["pipes"] = "a || b",
["neg"] = -42,
["float"] = 3.25,
["exp"] = 1.7944226813e+15,
["negexp"] = -1.5e-3,
["yes"] = true,
["no"] = false,
["gone"] = nil,
["list"] = {
"a", -- [1]
"b", -- [2]
"c", -- [3]
},
["sparse"] = {
[1] = "x",
[3] = "z",
},
["mixed"] = {
"pos1", -- [1]
["k"] = "v",
},
["empty"] = {
},
["nested"] = {
["deeper"] = {
["deepest"] = {
1, -- [1]
2, -- [2]
},
},
},
--[==[ a block comment with "quotes" and } braces ]==]
}
SecondVar = 7
