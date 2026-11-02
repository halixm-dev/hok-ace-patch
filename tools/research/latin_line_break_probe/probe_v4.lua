-- Latin line-break probe v4 (throwaway; never ship). Injected into UIPrefabClass by build_probe.py --v4.
-- The candidate fix plus logging. From the first UIPrefabClass:Create that has CoroutineService, it:
--   * resets the TextRendering flag every frame in LateUpdate (CoroutineService:AddLateUpdate), and
--   * tries to hook Canvas.preWillRenderCanvases, which runs right before UI text is laid out. There it
--     first measures the flag (a sample laid out with a break inside a word means on), logs when it is on,
--     then resets it. Without that hook the measurement runs in LateUpdate, before the reset.
-- Both are registered again when the Lua runner is replaced (re-login). Appends to
-- <persistentDataPath>/latin_line_break_probe_v4.txt.
local LATIN_V4_SAMPLE = "Every time 2 Chang'an Ancient Coins are played, this levels up and refreshes permanently."
local LATIN_V4_MAX_LINES = 400
local LATIN_V4_SUMMARY_FRAMES = 1800
local __latinV4 = {
    path = false, lines = 0, setFlag = nil, runner = false, lateUpdate = false, preRender = false,
    hookedPreRender = false, component = false, width = false, searched = false,
    frames = 0, lateCalls = 0, preCalls = 0, onAtCheck = 0, checks = 0,
}

local function __latinV4Write(line)
    if __latinV4.lines >= LATIN_V4_MAX_LINES then
        return
    end
    __latinV4.lines = __latinV4.lines + 1
    pcall(function()
        if not __latinV4.path then
            local dir = "/storage/emulated/0/Android/data/com.tencent.tmgp.osgame/files"
            pcall(function() dir = CS.UnityEngine.Application.persistentDataPath end)
            __latinV4.path = dir .. "/latin_line_break_probe_v4.txt"
        end
        local file = io.open(__latinV4.path, "a")
        if file then
            file:write(line, "\n")
            file:close()
        end
    end)
end

local function __latinV4Frame()
    local frame = -1
    pcall(function() frame = CS.UnityEngine.Time.frameCount end)
    return frame
end

local function __latinV4Component()
    local cached = __latinV4.component
    if cached then
        local ok, alive = pcall(function() return cached.font ~= nil and cached.isActiveAndEnabled end)
        if ok and alive then
            return cached
        end
    end
    __latinV4.component, __latinV4.width = false, false
    local frame = __latinV4Frame()
    if __latinV4.searched and frame - __latinV4.searched < 60 then
        return false
    end
    __latinV4.searched = frame
    pcall(function()
        local found = CS.UnityEngine.Object.FindObjectsOfType(typeof(CS.UnityEngine.UI.Text))
        for i = 0, found.Length - 1 do
            local candidate = found[i]
            if candidate.font ~= nil and candidate.isActiveAndEnabled then
                __latinV4.component = candidate
                break
            end
        end
    end)
    return __latinV4.component
end

-- true when the sample breaks inside a word (flag on), false when not, nil when it cannot tell.
local function __latinV4FlagOn()
    local component = __latinV4Component()
    if not component then
        return nil
    end
    local on = nil
    pcall(function()
        if not __latinV4.width then
            local settings = component:GetGenerationSettings(CS.UnityEngine.Vector2(0, 0))
            settings.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Overflow
            __latinV4.width = CS.UnityEngine.TextGenerator():GetPreferredWidth(LATIN_V4_SAMPLE, settings)
                / component.pixelsPerUnit * 0.22
        end
        local settings = component:GetGenerationSettings(CS.UnityEngine.Vector2(__latinV4.width, 4000))
        settings.horizontalOverflow = CS.UnityEngine.HorizontalWrapMode.Wrap
        settings.verticalOverflow = CS.UnityEngine.VerticalWrapMode.Overflow
        settings.richText = false
        settings.resizeTextForBestFit = false
        local generator = CS.UnityEngine.TextGenerator()
        generator:Populate(LATIN_V4_SAMPLE, settings)
        local lines = generator:GetLinesArray()
        local midword = 0
        for i = 1, lines.Length - 1 do
            local start = lines[i].startCharIdx
            if LATIN_V4_SAMPLE:sub(start, start):match("%a") and LATIN_V4_SAMPLE:sub(start + 1, start + 1):match("%a") then
                midword = midword + 1
            end
        end
        on = midword > 0
    end)
    return on
end

local function __latinV4Check(where)
    local on = __latinV4FlagOn()
    if on == nil then
        return
    end
    __latinV4.checks = __latinV4.checks + 1
    if on then
        __latinV4.onAtCheck = __latinV4.onAtCheck + 1
        __latinV4Write(string.format("frame %d\tflag ON at %s", __latinV4Frame(), where))
    end
end

local function __latinV4Summary()
    __latinV4.frames = __latinV4.frames + 1
    if __latinV4.frames % LATIN_V4_SUMMARY_FRAMES == 0 then
        __latinV4Write(string.format("frame %d\tsummary: lateUpdate %d, preWillRender %d, checks %d, flag on %d",
            __latinV4Frame(), __latinV4.lateCalls, __latinV4.preCalls, __latinV4.checks, __latinV4.onAtCheck))
    end
end

local function __latinV4Register()
    local runner = nil
    local ok, err = pcall(function() runner = CoroutineService:GetRunner() end)
    if not ok or runner == nil then
        return
    end
    if __latinV4.runner and __latinV4.runner == runner then
        local alive = false
        pcall(function() alive = CommonUtility:NotNull(runner) end)
        if alive then
            return
        end
    end
    __latinV4.runner = runner
    if __latinV4.setFlag == nil then
        __latinV4.setFlag = false
        pcall(function() __latinV4.setFlag = CS.UnityEngine.TextRendering.SetFlag end)
    end
    if not __latinV4.lateUpdate then
        __latinV4.lateUpdate = function()
            __latinV4.lateCalls = __latinV4.lateCalls + 1
            if not __latinV4.hookedPreRender then
                __latinV4Check("lateUpdate")
                __latinV4Summary()
            end
            if __latinV4.setFlag then
                pcall(__latinV4.setFlag, false)
            end
        end
    end
    local added, addErr = pcall(function() CoroutineService:AddLateUpdate(__latinV4.lateUpdate) end)
    __latinV4Write(string.format("frame %d\trunner %s\tAddLateUpdate %s", __latinV4Frame(), tostring(runner),
        added and "ok" or ("error " .. tostring(addErr))))

    if not __latinV4.hookedPreRender then
        __latinV4.preRender = function()
            __latinV4.preCalls = __latinV4.preCalls + 1
            __latinV4Check("preWillRenderCanvases")
            __latinV4Summary()
            if __latinV4.setFlag then
                pcall(__latinV4.setFlag, false)
            end
        end
        local hooked, hookErr = pcall(function()
            CS.UnityEngine.Canvas.preWillRenderCanvases("+", __latinV4.preRender)
        end)
        __latinV4.hookedPreRender = hooked
        __latinV4Write("Canvas.preWillRenderCanvases += " .. (hooked and "ok" or ("error " .. tostring(hookErr))))
    end
end

local function __LatinLineBreakProbeV4()
    if CoroutineService == nil then
        return
    end
    pcall(__latinV4Register)
end
