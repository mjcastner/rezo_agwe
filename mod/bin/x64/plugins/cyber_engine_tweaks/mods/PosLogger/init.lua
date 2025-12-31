local sessionStart = os.date("%Y-%m-%d_%H-%M-%S")
local dataFileName = "player_data_" .. sessionStart .. ".ndjson"
local debugFileName = "debug.log"
local logInterval = 1.0
local timer = 0

-- Helper: Write to debug log
local function LogDebug(msg)
    local f = io.open(debugFileName, "a+")
    if f then
        f:write("[" .. os.date("%H:%M:%S") .. "] " .. tostring(msg) .. "\n")
        f:close()
    end
end

-- Helper: Append JSON line
local function LogData(jsonString)
    local f = io.open(dataFileName, "a+")
    if f then
        f:write(jsonString .. "\n")
        f:close()
    end
end

-- Helper: Clean TweakDB IDs
local function CleanID(obj)
    if not obj then return "None" end
    local s, val = pcall(function() return obj.value end)
    if s and type(val) == "string" and val ~= "" then return val end
    local s2, id = pcall(function() return obj.id end)
    if s2 and id then
        local s3, val2 = pcall(function() return id.value end)
        if s3 and type(val2) == "string" and val2 ~= "" then return val2 end
    end
    -- Fallback regex to clean typical string output
    return tostring(obj):match("%-%-%[%[%s*(.-)%s*%]%]") or tostring(obj)
end

-- Helper: Escape strings for JSON (prevents quotes inside names breaking the JSON)
local function EscapeJSON(str)
    if type(str) ~= "string" then return tostring(str) end
    str = str:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r')
    return str
end

registerForEvent("onUpdate", function(dt)
    local ok, err = pcall(function()
        timer = timer + dt
        if timer < logInterval then return end
        timer = 0

        local player = Game.GetPlayer()
        if not player then return end

        local attached = false
        pcall(function() attached = player:IsAttached() end)
        if not attached then return end
        if Game.GetSystemRequestsHandler():IsPreGame() then return end

        -------------------------------------------------
        -- DATA GATHERING
        -------------------------------------------------

        -- 1. SPATIAL (Position & District)
        local pos = player:GetWorldPosition()
        if not pos or (math.abs(pos.x) < 0.1 and math.abs(pos.y) < 0.1) then return end
        
        local vel = player:GetVelocity()
        local speed = 0
        if vel then speed = math.sqrt(vel.x^2 + vel.y^2 + vel.z^2) end

        -- District Logic
        local districtName = "Unknown"
        local subDistrictName = "Unknown"
        
        local districtManager = player:GetPreventionSystem().districtManager
        local currentDistrict = districtManager and districtManager:GetCurrentDistrict()
        if currentDistrict then
            local districtRecord = TweakDBInterface.GetDistrictRecord(currentDistrict:GetDistrictID())
            if districtRecord then
                subDistrictName = Game.GetLocalizedText(districtRecord:LocalizedName())
                local parentRecord = districtRecord:ParentDistrict()
                if parentRecord then
                    districtName = Game.GetLocalizedText(parentRecord:LocalizedName())
                end
            end
        end

        -- 2. IDENTITY (Lifepath & Gender)
        local lifepath = "Unknown"
        local gender = "Unknown"
        
        local devSystem = Game.GetScriptableSystemsContainer():Get('PlayerDevelopmentSystem')
        local playerData = devSystem and devSystem:GetDevelopmentData(player)
        if playerData then
            lifepath = playerData:GetLifePath().value
        end
        
        local genderName = player:GetResolvedGenderName()
        if genderName then gender = tostring(genderName.value) end

        -- 3. STATUS (Combat, Vitals, Conditions)
        local combatStatus = player:IsInCombat()
        local isDead = player:IsDead()
        local isUnderwater = player:IsUnderwater()
        
        -- 4. STATS & ATTRIBUTES
        local stats = Game.GetStatsSystem()
        local eid = player:GetEntityID()
        
        -- Default values
        local s_level, s_cred, s_health, s_mem, s_carry = 0,0,0,0,0
        local a_body, a_cool, a_int, a_ref, a_tech = 0,0,0,0,0

        if stats and eid then
            -- Proficiency
            s_level = stats:GetStatValue(eid, gamedataStatType.Level) or 0
            s_cred = stats:GetStatValue(eid, gamedataStatType.StreetCred) or 0
            
            -- Vitals
            s_health = stats:GetStatValue(eid, gamedataStatType.Health) or 0
            s_mem = stats:GetStatValue(eid, gamedataStatType.Memory) or 0
            s_carry = stats:GetStatValue(eid, gamedataStatType.CarryCapacity) or 0

            -- Attributes
            a_body = stats:GetStatValue(eid, gamedataStatType.Strength) or 0
            a_cool = stats:GetStatValue(eid, gamedataStatType.Cool) or 0
            a_int = stats:GetStatValue(eid, gamedataStatType.Intelligence) or 0
            a_ref = stats:GetStatValue(eid, gamedataStatType.Reflexes) or 0
            a_tech = stats:GetStatValue(eid, gamedataStatType.TechnicalAbility) or 0
        end

        -- 5. LOADOUT (Clothing, Weapons, Vehicle, Money)
        local inVehicle = false
        local vehicleName = "None"
        local veh = Game.GetMountedVehicle(player)
        if veh then
            inVehicle = true
            vehicleName = CleanID(veh:GetRecordID())
        end

        local money = 0
        local activeWeapon = "None"
        local clothing = {Head="Empty", Eyes="Empty", Chest="Empty", Legs="Empty", Feet="Empty", Torso="Empty", Outfit="Empty"}
        
        local trans = Game.GetTransactionSystem()
        if trans then
            money = trans:GetItemQuantity(player, ItemID.new(TweakDBID.new("Items.money")))
            local weaponObj = ScriptedPuppet.GetWeaponRight(player)
            if weaponObj then activeWeapon = CleanID(weaponObj:GetItemID()) end

            local slots = {
                Head="AttachmentSlots.Head", Eyes="AttachmentSlots.Eyes",
                Chest="AttachmentSlots.Chest", Legs="AttachmentSlots.Legs",
                Feet="AttachmentSlots.Feet", Torso="AttachmentSlots.Torso",
                Outfit="AttachmentSlots.Outfit"
            }
            for k, s in pairs(slots) do
                local item = trans:GetItemInSlot(player, TweakDBID.new(s))
                if item then clothing[k] = CleanID(item:GetItemID()) end
            end
        end

        -- 6. NARRATIVE (Quests)
        local questTitle = "None"
        local questObj = "None"
        local journal = Game.GetJournalManager()
        if journal then
            local tracked = journal:GetTrackedEntry()
            if tracked then 
                -- Get Objective Description
                local questDescLocID = tracked:GetDescription()
                if questDescLocID then
                    questObj = Game.GetLocalizedText(questDescLocID)
                end

                -- Get Parent Quest Title
                local questID = journal:GetParentEntry(tracked)
                if questID then
                    local questEntry = journal:GetParentEntry(questID)
                    if questEntry then
                        local questLocID = questEntry:GetTitle(journal)
                        if questLocID then
                            questTitle = Game.GetLocalizedText(questLocID)
                        end
                    end
                end
            end
        end

        -------------------------------------------------
        -- JSON CONSTRUCTION
        -------------------------------------------------
        -- We construct sub-objects first for cleanliness
        
        local json_spatial = string.format(
            '{"x":%.2f,"y":%.2f,"z":%.2f,"speed":%.2f,"district":"%s","subDistrict":"%s"}',
            pos.x, pos.y, pos.z, speed, EscapeJSON(districtName), EscapeJSON(subDistrictName)
        )

        local json_identity = string.format(
            '{"lifepath":"%s","gender":"%s"}',
            EscapeJSON(lifepath), EscapeJSON(gender)
        )

        local json_proficiency = string.format(
            '{"level":%d,"streetCred":%d}',
            s_level, s_cred
        )

        local json_attributes = string.format(
            '{"body":%d,"cool":%d,"intelligence":%d,"reflexes":%d,"tech":%d}',
            a_body, a_cool, a_int, a_ref, a_tech
        )

        local json_status = string.format(
            '{"health":%.1f,"memory":%d,"isCombat":%s,"isDead":%s,"isUnderwater":%s}',
            s_health, s_mem, tostring(combatStatus), tostring(isDead), tostring(isUnderwater)
        )

        local json_loadout = string.format(
            '{"activeWeapon":"%s","equippedVehicle":"%s","isMounted":%s,"carryCapacity":%d}',
            EscapeJSON(activeWeapon), EscapeJSON(vehicleName), tostring(inVehicle), s_carry
        )
        
        local json_clothing = string.format(
            '{"head":"%s","eyes":"%s","chest":"%s","legs":"%s","feet":"%s","torso":"%s","outfit":"%s"}',
            clothing.Head, clothing.Eyes, clothing.Chest, clothing.Legs, clothing.Feet, clothing.Torso, clothing.Outfit
        )

        local json_economy = string.format(
            '{"euroDollars":%d}',
            money
        )

        local json_narrative = string.format(
            '{"questTitle":"%s","questObjective":"%s"}',
            EscapeJSON(questTitle), EscapeJSON(questObj)
        )

        -- Master Assembly
        local jsonLine = string.format(
            '{"timestamp":"%s","spatial":%s,"identity":%s,"proficiency":%s,"attributes":%s,"status":%s,"loadout":%s,"clothing":%s,"economy":%s,"narrative":%s}',
            os.date("%Y-%m-%dT%H:%M:%S"),
            json_spatial,
            json_identity,
            json_proficiency,
            json_attributes,
            json_status,
            json_loadout,
            json_clothing,
            json_economy,
            json_narrative
        )

        LogData(jsonLine)
    end)

    if not ok then
        LogDebug("CRITICAL ERROR: " .. tostring(err))
    end
end)