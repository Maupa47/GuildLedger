----------------------------------------------------------------------
-- Amazing Hub - "×" to clear a search, and one click back to the whole member list (Amazing Forever Guild Pack
-- 0.8.0; our own file, not upstream)
--
-- H3 (PLAN_COMMUNITY W13). Every one-line field with a grey hint text (UI:CreateInput with `placeholder`: the
-- search fields) shows an "×" at its right end while it holds text; a click empties it, which runs the field's
-- own OnTextChanged, so the list it filters refreshes as when the text is deleted by hand.
-- The member list has its own Reset button for rank, class, search and sort (tools/rebrand-hub.py, H35).
--
-- Copied in by tools/rebrand-hub.py from addon/hub-extra/; edit it there.
----------------------------------------------------------------------
local UI = AmazingHub.UI
local Clear = {}
AmazingHub.PackClear = Clear

-- Puts the "×" on `box`. `box.packActive()` (optional): something besides the text is filtering.
-- `box.packReset()` (optional): clears that too.
function Clear.Attach(box)
    if type(box) ~= "table" or box.packClear or type(CreateFrame) ~= "function" then return nil end
    local b = CreateFrame("Button", nil, box)
    b:SetSize(18, 18)
    b:SetPoint("RIGHT", box, "RIGHT", -2, 0)
    local x = UI.CreateText and UI:CreateText(b, "\195\151", 14) -- U+00D7 multiplication sign
    if x then x:SetPoint("CENTER", 0, 0) end
    b.label = x
    local function sync()
        local text = box:GetText() or ""
        b:SetShown(text ~= "" or (box.packActive ~= nil and box.packActive() == true))
    end
    b:SetScript("OnClick", function()
        if box.packReset then box.packReset() end
        box:SetText("")
        box:ClearFocus()
        sync()
    end)
    box:HookScript("OnTextChanged", sync)
    if box.SetTextInsets then box:SetTextInsets(6, 22, 0, 0) end
    box.packClear, box.packSync = b, sync
    sync()
    return b
end

local make = UI.CreateInput
if make then
    function UI:CreateInput(parent, width, height, opts)
        local box = make(self, parent, width, height, opts)
        if type(opts) == "table" and opts.placeholder and not opts.multiline and not opts.numeric then
            Clear.Attach(box)
        end
        return box
    end
end
