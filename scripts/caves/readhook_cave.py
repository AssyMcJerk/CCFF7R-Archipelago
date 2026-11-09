from keystone import *; from capstone import *
import struct
NATIVES=[0x254,0x256,0x24A,0x24C,0x24E,0x169,0x17C,0x251,0x29A,0x33A,0x3E3,0x3E4,0x3F8,0x403,0x25B,0x156,0x154]
TBL=0xC0
def build(d_tbl,d_data,d_ret):
    code=f"""
push rcx
lea rcx, [rip + {d_tbl}]
scan:
mov ax, word ptr [rcx]
test ax, ax
jz miss
cmp ax, dx
je hit
add rcx, 2
jmp scan
miss:
pop rcx
jmp orig
hit:
pop rcx
push rcx
push r9
push rax
push r10
push r11
lea rcx, [rip + {d_data}]
mov eax, dword ptr [rcx+8]
and eax, 0xFF
lea r10, [rcx+rax*8+0x10]
mov word ptr [r10], dx
mov dword ptr [r10+2], 0
mov word ptr [r10+6], 0
mov r9, qword ptr [rbx+0x18]
movsxd rax, dword ptr [rbx+0x24]
test eax, eax
jle fin
mov r11, qword ptr [r9+rax*8-8]
mov word ptr [r10+2], r11w
cmp eax, 1
jle fin
mov r11, qword ptr [r9+rax*8-16]
mov word ptr [r10+4], r11w
cmp eax, 2
jle fin
mov r11, qword ptr [r9+rax*8-24]
mov word ptr [r10+6], r11w
fin:
inc dword ptr [rcx+8]
pop r11
pop r10
pop rax
pop r9
pop rcx
orig:
movsxd rax, edx
mov rax, qword ptr [r8+rax*8]
jmp qword ptr [rip + {d_ret}]
"""
    ks=Ks(KS_ARCH_X86,KS_MODE_64); enc,_=ks.asm(code,0); return bytes(enc)
cs=Cs(CS_ARCH_X86,CS_MODE_64)
b=build(0,0,0)
for _ in range(4):
    ins=list(cs.disasm(b,0))
    leas=[i for i in ins if i.mnemonic=='lea' and 'rip' in i.op_str]; jmp=ins[-1]
    b=build(TBL-(leas[0].address+leas[0].size), 0x100-(leas[1].address+leas[1].size), 0xF0-(jmp.address+jmp.size))
assert len(b) < TBL, len(b)
page=bytearray(0xF0); page[:len(b)]=b
struct.pack_into(f"<{len(NATIVES)+1}H", page, TBL, *NATIVES, 0)
print(len(b)); open('cave5.hex','w').write(bytes(page).hex())
