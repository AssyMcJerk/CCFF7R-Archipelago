# v0.6.37 jump cave (APJMPHK2): gate_to bit 31 set = bounce with flag 0 (scene's own entrance) instead of flag 1
from keystone import *; from capstone import *
def build(d_data, d_ret):
    code=f"""
push rax
lea rax, [rip + {d_data}]
mov dword ptr [rax+0x20], edx
inc dword ptr [rax+0x24]
mov ecx, dword ptr [rax+8]
test ecx, ecx
je warp
cmp edx, ecx
jne warp
mov edx, dword ptr [rax+0xc]
mov r8d, 1
btr edx, 31
jnc keep
xor r8d, r8d
keep:
inc dword ptr [rax+0x1c]
jmp done
warp:
mov ecx, dword ptr [rax+0x10]
test ecx, ecx
je done
cmp edx, 0x157c
jb done
cmp edx, 0x16a8
jae done
mov dword ptr [rax+0x18], edx
mov edx, ecx
xor r8d, r8d
mov dword ptr [rax+0x10], 0
inc dword ptr [rax+0x14]
done:
mov rcx, qword ptr [rax-0x10]
mov rcx, qword ptr [rcx]
pop rax
jmp qword ptr [rip + {d_ret}]
"""
    return bytes(Ks(KS_ARCH_X86,KS_MODE_64).asm(code,0)[0])
cs=Cs(CS_ARCH_X86,CS_MODE_64); b=build(0,0)
for _ in range(3):
    ins=list(cs.disasm(b,0)); lea=ins[1]; j=ins[-1]
    b=build(0x100-(lea.address+lea.size), 0xF8-(j.address+j.size))
assert len(b)<0xF0; print(len(b)); open('jumpcave2.hex','w').write(b.hex())
