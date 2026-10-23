-- Latin line-break probe (throwaway; never ship). Injected into PVPRankDataClass by build_probe.py.
-- Runs once, the first time the lobby draws a rank title. Lays out one English sentence with the engine's
-- TextGenerator before and after TextRendering.SetFlag, leaves the flag at LATIN_PROBE_FINAL, and writes
-- everything to <persistentDataPath>/latin_line_break_probe.txt.
local LATIN_PROBE_FINAL = false
local LATIN_PROBE_SAMPLE = "Every time 2 Chang'an Ancient Coins are played, this levels up and refreshes permanently. Tiers 3-5 gain 12/34 refreshes."
local __latinProbeDone = false
local __latinProbeLines = {}

local function __latinProbeLog(line)
    __latinProbeLines[#__latinProbeLines + 1] = line
    pcall(print, "[LatinLineBreakProbe] " .. line)
end

local function __latinProbeFlush()
    local text = table.concat(__latinProbeLines, "\n") .. "\n"
    local dirs = {}
    pcall(function() dirs[#dirs + 1] = CS.UnityEngine.Application.persistentDataPath end)
    dirs[#dirs + 1] = "/storage/emulated/0/Android/data/com.tencent.tmgp.osgame/files"
    for _, dir in ipairs(dirs) do
        local ok, file = pcall(io.open, dir .. "/latin_line_break_probe.txt", "a")
        if ok and file then
            file:write(text)
            file:close()
            return
        end
    end
    pcall(function() CS.UnityEngine.Debug.LogError("[LatinLineBreakProbe] no writable file\n" .. text) end)
end

-- One layout of the sample at <width> (layout units): the lines, and how many breaks fall inside a word.
local function __latinProbeLayout(label, component, width)
    local ok, err = pcall(function()
        local settings = component:GetGenerationSettings(CS.UnityEngine.Vector2(width, 4000))
        settings.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Wrap
        settings.verticalOverflow = CS.UnityEngine.VerticalWrapMode.Overflow
        settings.richText = false
        settings.resizeTextForBestFit = false
        local generator = CS.UnityEngine.TextGenerator()
        generator:Populate(LATIN_PROBE_SAMPLE, settings)
        local lines = generator:GetLinesArray()
        local starts = {}
        for i = 0, lines.Length - 1 do
            starts[#starts + 1] = lines[i].startCharIdx
        end
        local pieces, midword = {}, 0
        for i, start in ipairs(starts) do
            local stop = starts[i + 1] or #LATIN_PROBE_SAMPLE
            pieces[#pieces + 1] = "[" .. LATIN_PROBE_SAMPLE:sub(start + 1, stop) .. "]"
            if i > 1 then
                local before, after = LATIN_PROBE_SAMPLE:sub(start, start), LATIN_PROBE_SAMPLE:sub(start + 1, start + 1)
                if before:match("%a") and after:match("%a") then
                    midword = midword + 1
                end
            end
        end
        __latinProbeLog(string.format("%s width=%.1f lines=%d midword=%d %s", label, width, #starts, midword,
            table.concat(pieces, " ")))
    end)
    if not ok then
        __latinProbeLog(label .. " layout failed: " .. tostring(err))
    end
end

local function __latinProbeMeasure(label, component, widths)
    for _, width in ipairs(widths) do
        __latinProbeLayout(label, component, width)
    end
end

local function __LatinLineBreakProbe()
    if __latinProbeDone then
        return
    end
    __latinProbeDone = true
    pcall(function()
        __latinProbeLog("---- probe " .. os.date("%Y-%m-%d %H:%M:%S") .. " final flag " .. tostring(LATIN_PROBE_FINAL))

        local rendering
        local ok, err = pcall(function() rendering = CS.UnityEngine.TextRendering end)
        __latinProbeLog("TextRendering type: " .. (ok and tostring(rendering) or ("error " .. tostring(err))))
        local setFlag
        if rendering then
            ok, err = pcall(function() setFlag = rendering.SetFlag end)
            __latinProbeLog("TextRendering.SetFlag: " .. (ok and tostring(setFlag) or ("error " .. tostring(err))))
        end

        local component
        ok, err = pcall(function()
            local found = CS.UnityEngine.Object.FindObjectsOfType(typeof(CS.UnityEngine.UI.Text))
            for i = 0, found.Length - 1 do
                local candidate = found[i]
                if candidate.font ~= nil and candidate.isActiveAndEnabled then
                    component = candidate
                    break
                end
            end
        end)
        if component then
            __latinProbeLog(string.format("font from Text '%s': %s size %s", tostring(component.name),
                tostring(component.font.name), tostring(component.fontSize)))
        else
            __latinProbeLog("no active UI.Text found: " .. tostring(err))
        end

        local widths = {}
        if component then
            pcall(function()
                local settings = component:GetGenerationSettings(CS.UnityEngine.Vector2(0, 0))
                settings.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow
                local full = CS.UnityEngine.TextGenerator():GetPreferredWidth(LATIN_PROBE_SAMPLE, settings)
                    / component.pixelsPerUnit
                __latinProbeLog(string.format("one-line width %.1f", full))
                widths = { full * 0.22, full * 0.35, full * 0.5 }
            end)
            __latinProbeMeasure("before", component, widths)
        end

        if setFlag then
            for _, value in ipairs({ true, false }) do
                ok, err = pcall(setFlag, value)
                __latinProbeLog(string.format("SetFlag(%s): %s", tostring(value), ok and "ok" or ("error " .. tostring(err))))
                if component and ok then
                    __latinProbeMeasure("flag=" .. tostring(value), component, widths)
                end
            end
            if LATIN_PROBE_FINAL then
                ok, err = pcall(setFlag, true)
                __latinProbeLog("SetFlag(true) as final: " .. (ok and "ok" or ("error " .. tostring(err))))
            end
        end
    end)
    __latinProbeFlush()
end

pcall(function()
    __latinProbeLog("---- script loaded " .. os.date("%Y-%m-%d %H:%M:%S"))
    __latinProbeFlush()
    __latinProbeLines = {}
end)

