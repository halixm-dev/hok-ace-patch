-- Latin line-break probe v3 (throwaway; never ship). Injected into UIPrefabClass by build_probe.py --v3.
-- Once, at the first UIPrefabClass:Create that has AssetService and a live UI.Text: read which copy of
-- Font/NumberCharacters the game serves, lay out one English sentence with the flag on, feed that asset to
-- TextRendering.LoadLinebreakingRules(nil, nil, asset) and lay it out again, then leave the flag off.
-- Appends to <persistentDataPath>/latin_line_break_probe_v3.txt.
local LATIN_V3_SAMPLE = "Every time 2 Chang'an Ancient Coins are played, this levels up and refreshes permanently."
local LATIN_V3_ASSET = "Font/NumberCharacters"
local __latinV3 = { done = false, tries = 0, path = false }

local function __latinV3Write(line)
    pcall(function()
        if not __latinV3.path then
            local dir = "/storage/emulated/0/Android/data/com.tencent.tmgp.osgame/files"
            pcall(function() dir = CS.UnityEngine.Application.persistentDataPath end)
            __latinV3.path = dir .. "/latin_line_break_probe_v3.txt"
        end
        local file = io.open(__latinV3.path, "a")
        if file then
            file:write(line, "\n")
            file:close()
        end
    end)
end

local function __latinV3Component()
    local component = nil
    pcall(function()
        local found = CS.UnityEngine.Object.FindObjectsOfType(typeof(CS.UnityEngine.UI.Text))
        for i = 0, found.Length - 1 do
            local candidate = found[i]
            if candidate.font ~= nil and candidate.isActiveAndEnabled then
                component = candidate
                break
            end
        end
    end)
    return component
end

-- The sample's lines at three widths, and how many breaks fall between two letters.
local function __latinV3Layout(component, label)
    local ok, err = pcall(function()
        local settings = component:GetGenerationSettings(CS.UnityEngine.Vector2(0, 0))
        settings.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow
        local full = CS.UnityEngine.TextGenerator():GetPreferredWidth(LATIN_V3_SAMPLE, settings)
            / component.pixelsPerUnit
        for _, share in ipairs({ 0.22, 0.35, 0.5 }) do
            local wrap = component:GetGenerationSettings(CS.UnityEngine.Vector2(full * share, 4000))
            wrap.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Wrap
            wrap.verticalOverflow = CS.UnityEngine.VerticalWrapMode.Overflow
            wrap.richText = false
            wrap.resizeTextForBestFit = false
            local generator = CS.UnityEngine.TextGenerator()
            generator:Populate(LATIN_V3_SAMPLE, wrap)
            local lines = generator:GetLinesArray()
            local parts, midword, previous = {}, 0, 1
            for i = 1, lines.Length - 1 do
                local start = lines[i].startCharIdx
                parts[#parts + 1] = LATIN_V3_SAMPLE:sub(previous, start)
                previous = start + 1
                if LATIN_V3_SAMPLE:sub(start, start):match("%a") and LATIN_V3_SAMPLE:sub(start + 1, start + 1):match("%a") then
                    midword = midword + 1
                end
            end
            parts[#parts + 1] = LATIN_V3_SAMPLE:sub(previous)
            __latinV3Write(string.format("%s\twidth %.0f\tmidword %d\t%s", label, full * share, midword,
                table.concat(parts, " | ")))
        end
    end)
    if not ok then
        __latinV3Write(label .. "\tlayout error " .. tostring(err))
    end
end

local function __LatinLineBreakProbeV3()
    if __latinV3.done or __latinV3.tries >= 200 then
        return
    end
    __latinV3.tries = __latinV3.tries + 1
    if AssetService == nil then
        return
    end
    local component = __latinV3Component()
    if not component then
        return
    end
    __latinV3.done = true
    __latinV3Write("---- probe v3 session, create " .. tostring(__latinV3.tries) .. ", clock " .. tostring(os.clock()))

    local rendering, setFlag, load = nil, nil, nil
    pcall(function() rendering = CS.UnityEngine.TextRendering end)
    pcall(function() setFlag = rendering.SetFlag end)
    pcall(function() load = rendering.LoadLinebreakingRules end)
    __latinV3Write("SetFlag " .. tostring(setFlag) .. "\tLoadLinebreakingRules " .. tostring(load))

    -- Which copy does the game serve? The APK's has 99 bytes and no letters; the patched one has "A".
    local asset, content, text = nil, nil, nil
    local ok, err = pcall(function()
        asset = AssetService:LoadPrimitiveAsset(LATIN_V3_ASSET, LifeType.Immediate)
        content = asset and asset.Resource and asset.Resource.Content
        text = content and content.text
    end)
    if ok and text then
        __latinV3Write(string.format("asset %s: %d bytes, has A %s, has z %s, has apostrophe %s", LATIN_V3_ASSET,
            #text, tostring(text:find("A", 1, true) ~= nil), tostring(text:find("z", 1, true) ~= nil),
            tostring(text:find("'", 1, true) ~= nil)))
    else
        __latinV3Write("asset " .. LATIN_V3_ASSET .. ": not read (" .. tostring(err or "no text") .. ")")
    end

    if setFlag then
        pcall(setFlag, true)
        __latinV3Layout(component, "flag on, as loaded")
    end
    if load and content then
        local loaded, loadErr = pcall(load, nil, nil, content)
        __latinV3Write("LoadLinebreakingRules(nil, nil, asset): " .. (loaded and "ok" or ("error " .. tostring(loadErr))))
        if loaded and setFlag then
            pcall(setFlag, true)
            __latinV3Layout(component, "flag on, after load")
        end
    end
    if setFlag then
        pcall(setFlag, false)
        __latinV3Layout(component, "flag off")
    end
    pcall(function() if asset then AssetService:Unload(asset) end end)
    __latinV3Write("---- probe v3 done")
end
