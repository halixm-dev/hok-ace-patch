-- Latin line-break probe v2 (throwaway; never ship). Injected into UIPrefabClass by build_probe.py --v2.
-- On every UIPrefabClass:Create, before the prefab initialises: lay out one English sentence to read the
-- TextRendering flag (a break inside a word means it is on), log it with the prefab's class and path,
-- then call SetFlag(false). Appends to <persistentDataPath>/latin_line_break_probe_v2.txt.
local LATIN_V2_SAMPLE = "Every time 2 Chang'an Ancient Coins are played, this levels up and refreshes permanently."
local LATIN_V2_MAX_EVENTS = 2000
local __latinV2 = { events = 0, width = false, component = false, setFlag = false, path = false }

local function __latinV2Write(line)
    pcall(function()
        if not __latinV2.path then
            local dir = "/storage/emulated/0/Android/data/com.tencent.tmgp.osgame/files"
            pcall(function() dir = CS.UnityEngine.Application.persistentDataPath end)
            __latinV2.path = dir .. "/latin_line_break_probe_v2.txt"
        end
        local file = io.open(__latinV2.path, "a")
        if file then
            file:write(line, "\n")
            file:close()
        end
    end)
end

-- A live UI.Text to borrow a font from; found again whenever the cached one is gone.
local function __latinV2Component()
    local cached = __latinV2.component
    if cached then
        local ok, alive = pcall(function() return cached.font ~= nil and cached.isActiveAndEnabled end)
        if ok and alive then
            return cached
        end
    end
    __latinV2.component, __latinV2.width = false, false
    pcall(function()
        local found = CS.UnityEngine.Object.FindObjectsOfType(typeof(CS.UnityEngine.UI.Text))
        for i = 0, found.Length - 1 do
            local candidate = found[i]
            if candidate.font ~= nil and candidate.isActiveAndEnabled then
                __latinV2.component = candidate
                break
            end
        end
    end)
    return __latinV2.component
end

-- "on", "off" or "?" : whether the sample breaks inside a word at a narrow width.
local function __latinV2Flag()
    local component = __latinV2Component()
    if not component then
        return "?"
    end
    local state = "?"
    pcall(function()
        if not __latinV2.width then
            local settings = component:GetGenerationSettings(CS.UnityEngine.Vector2(0, 0))
            settings.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow
            __latinV2.width = CS.UnityEngine.TextGenerator():GetPreferredWidth(LATIN_V2_SAMPLE, settings)
                / component.pixelsPerUnit * 0.22
        end
        local settings = component:GetGenerationSettings(CS.UnityEngine.Vector2(__latinV2.width, 4000))
        settings.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Wrap
        settings.verticalOverflow = CS.UnityEngine.VerticalWrapMode.Overflow
        settings.richText = false
        settings.resizeTextForBestFit = false
        local generator = CS.UnityEngine.TextGenerator()
        generator:Populate(LATIN_V2_SAMPLE, settings)
        local lines = generator:GetLinesArray()
        local midword = 0
        for i = 1, lines.Length - 1 do
            local start = lines[i].startCharIdx
            if LATIN_V2_SAMPLE:sub(start, start):match("%a") and LATIN_V2_SAMPLE:sub(start + 1, start + 1):match("%a") then
                midword = midword + 1
            end
        end
        state = midword > 0 and "on" or "off"
    end)
    return state
end

local function __LatinLineBreakProbeV2(prefab, resourcePath)
    if __latinV2.events >= LATIN_V2_MAX_EVENTS then
        if __latinV2.setFlag then
            pcall(__latinV2.setFlag, false)
        end
        return
    end
    __latinV2.events = __latinV2.events + 1
    pcall(function()
        if __latinV2.events == 1 then
            __latinV2Write("---- probe v2 session, clock " .. tostring(os.clock()))
            local ok, err = pcall(function() __latinV2.setFlag = CS.UnityEngine.TextRendering.SetFlag end)
            __latinV2Write("SetFlag: " .. (ok and tostring(__latinV2.setFlag) or ("error " .. tostring(err))))
        end
        local state = __latinV2Flag()
        local ok, err = true, nil
        if __latinV2.setFlag then
            ok, err = pcall(__latinV2.setFlag, false)
        end
        -- The previous create left the flag off, so "on" here means something turned it on since.
        local mark = state == "on" and "\t<<< flag was ON" or ""
        __latinV2Write(string.format("%d\t%.2f\t%s\t%s\t%s%s%s", __latinV2.events, os.clock(), state,
            tostring(prefab and prefab.classname), tostring(resourcePath),
            ok and "" or ("\tSetFlag error " .. tostring(err)), mark))
    end)
end

