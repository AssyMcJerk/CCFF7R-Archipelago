-- Write the mapjump_gate_test v2 log to dumps\mapjump_hist.txt
local OUT  = [[C:\CCFF7R_dumps\mapjump_hist.txt]]
local base = getAddress('"CCFF7R-Win64-Shipping.exe"')
local n    = readInteger('mj_n')
local h    = getAddress('mj_hist')
local f    = io.open(OUT, 'w')
f:write(string.format('jumps logged: %d   [71B4B98] = %d   story = %d   map = %d\n', n,
  readInteger(base + 0x71B4B98), readInteger(base + 0x71B4EF8), readInteger(base + 0x71B4EFC)))
for i = math.max(0, n - 64), n - 1 do
  local e = h + (i % 64) * 16
  local id, flag, ret = readInteger(e), readInteger(e + 4), readQword(e + 8)
  f:write(string.format('%d\tid=%d (0x%X)\tflag=%d\tcaller=exe+%X\n', i, id, id, flag & 0xFF, ret - base))
end
f:close()
print('wrote mapjump_hist.txt (' .. n .. ' jumps)')
