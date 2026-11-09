-- Dump the native_trace.cea (v2) ring buffer to dumps\native_trace_N.bin (run from the Lua window).
local OUT = [[C:\CCFF7R_dumps\]]
local buf = getAddress('nt_buf')
_G.ntN = (_G.ntN or 0) + 1
local b = readBytes(buf, 0x200020, true)
local f = io.open(OUT .. 'native_trace_v2_' .. _G.ntN .. '.bin', 'wb')
f:write(string.char(table.unpack(b, 1, 1)))
for i = 2, #b, 4096 do
  f:write(string.char(table.unpack(b, i, math.min(i + 4095, #b))))
end
f:close()
print(string.format('wrote native_trace_v2_%d.bin  (%d calls logged)', _G.ntN, readInteger(buf)))
