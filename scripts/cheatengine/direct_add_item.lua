-- CCFF7R: add an item by writing the inventory array directly (no game code called).
-- Mirrors ChangeItemCount (exe+116F7C0). Works for consumables (0x2xxx), key/other (0x3xxx), accessories (0x5xxx).
-- Container: +0x00 u32 type (id>>12), +0x28 ptr records, +0x30 i32 slots, +0x34 i32 min (empty if count<=min), +0x38 i32 max
-- Record (8 bytes): u16 id, u16 count, u16 acquisition order (1 = newest), u8 new flag, u8 pad
local base = getAddress('"CCFF7R-Win64-Shipping.exe"')
local CONT = { [2] = 0x71AAE20, [3] = 0x71AAE60, [5] = 0x71AADE0 }

function directAdd(id, n)
  local c = base + CONT[id >> 12]
  assert(readInteger(c) == (id >> 12), 'container type mismatch')
  local recs, slots = readQword(c + 0x28), readInteger(c + 0x30)
  local minc, maxc  = readInteger(c + 0x34), readInteger(c + 0x38)
  local hit, free
  for i = 0, slots - 1 do
    local r = recs + i * 8
    local rid, cnt = readSmallInteger(r), readSmallInteger(r + 2)
    if cnt > minc and rid == id then hit = r break end
    if not free and cnt <= minc then free = r end
  end
  local r = hit or free
  if not r then print('inventory full') return end
  if not hit then
    for i = 0, slots - 1 do                       -- age every other owned item by one
      local o = recs + i * 8
      if readSmallInteger(o + 2) > minc then writeSmallInteger(o + 4, readSmallInteger(o + 4) + 1) end
    end
    writeSmallInteger(r + 4, 1); writeBytes(r + 6, 1)   -- newest + "new" flag
  end
  local cnt = (hit and readSmallInteger(r + 2) or 0) + n
  if cnt > maxc then cnt = maxc end
  writeSmallInteger(r, id); writeSmallInteger(r + 2, cnt)
  print(string.format('%04X -> count %d (%s)', id, cnt, hit and 'stacked' or 'new slot'))
end


-- Materia (0x4xxx). Mirrors exe+1394400 for a plain id (no preset): 1 star, default bonus.
-- Container 71AAF20: +0x10 defs ptr (0x28 stride), +0x18 def count, +0x28 records (0x10 stride), +0x30 slots, +0x34 min
-- Record: +0 u16 id, +2 u8 count, +4 u16 order (1 = newest), +6 u8 new, +7 u8 def[+0x18],
--         +8 u16 def[+0x08], +A u8 stars 1-5, +B u8 0xFF, +C u16 bonus type 0-7, +E u16 bonus value 0-100
function directAddMateria(id, stars, btype, bval)
  local c = base + 0x71AAF20
  assert(readInteger(c) == 4, 'materia container type mismatch')
  local idx = id & 0xFFF
  assert(idx < readInteger(c + 0x18), 'unknown materia id')
  local def = readQword(c + 0x10) + idx * 0x28
  local recs, slots, minc = readQword(c + 0x28), readInteger(c + 0x30), readInteger(c + 0x34)
  local r
  for i = 0, slots - 1 do
    if readBytes(recs + i * 0x10 + 2, 1) <= minc then r = recs + i * 0x10 break end
  end
  if not r then print('materia list full') return end
  for i = 0, slots - 1 do                       -- age every owned materia by one
    local o = recs + i * 0x10
    if readSmallInteger(o) ~= 0 and readBytes(o + 2, 1) > minc then
      writeSmallInteger(o + 4, readSmallInteger(o + 4) + 1)
    end
  end
  writeSmallInteger(r, id)
  writeBytes(r + 2, 1, 0)                       -- count 1, pad
  writeSmallInteger(r + 4, 1); writeBytes(r + 6, 1)
  writeBytes(r + 7, readBytes(def + 0x18, 1))
  writeSmallInteger(r + 8, readSmallInteger(def + 8))
  writeBytes(r + 0xA, math.max(1, math.min(5, stars or 1)), 0xFF)
  writeSmallInteger(r + 0xC, btype or readSmallInteger(def + 0xC))
  writeSmallInteger(r + 0xE, bval  or readSmallInteger(def + 0xE))
  print(string.format('materia %04X added at slot %d', id, (r - recs) // 0x10))
end

-- test: a materia you don't own yet
directAddMateria(0x4002)   -- Thunder
