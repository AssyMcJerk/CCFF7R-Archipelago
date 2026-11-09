-- DeathLink tests. Set MODE below, then Execute while in a battle.
--   MODE = "info"   : just print the battle globals (run this in a normal field battle AND in a mission battle)
--   MODE = "finish" : what BtlSetFinishGameOver does (needs active ~= 0): side 0, type 3, state 3 -> 4
--   MODE = "flag1"  : HP 0 + actor flag bit 0x01   (the game treats (flags & 0x11) like "dead")
--   MODE = "flag10" : HP 0 + actor flag bit 0x10
local MODE = "info"
local b = getAddress("CCFF7R-Win64-Shipping.exe")
local active, state, ftype = b + 0x717AD52, b + 0x717AD5C, b + 0x717AD64
local hp, flags = b + 0x718DC28, b + 0x718DC8A       -- Zack = battle actor 0 (0x718DA40): HP +0x1E8, flags +0x24A
print(string.format("active=%d state=%d type=%d result=%d  hp=%d flags=%04X",
  readBytes(active, 1), readInteger(state), readInteger(ftype), readInteger(b + 0x717AD60),
  readInteger(hp), readSmallInteger(flags)))
if MODE == "finish" then
  writeInteger(hp, 0); writeBytes(b + 0x717AD55, 0); writeInteger(ftype, 3); writeInteger(state, 4)
  print("finish written")
elseif MODE == "flag1" then
  writeInteger(hp, 0); writeSmallInteger(flags, readSmallInteger(flags) | 0x01); print("hp 0 + flag 0x01")
elseif MODE == "flag10" then
  writeInteger(hp, 0); writeSmallInteger(flags, readSmallInteger(flags) | 0x10); print("hp 0 + flag 0x10")
end
