#!/usr/bin/env python3
"""Execute the added x86 code in Unicorn with mocked GoldSrc engine callbacks.
This is NOT a Windows-loader or Half-Life gameplay test.
"""
from pathlib import Path
import json, os, struct, unittest
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

HERE = Path(__file__).resolve().parent
META = json.loads((HERE / 'build/build.json').read_text())
DLL = Path(os.environ.get('MC_PATCHED_DLL', HERE / 'package/BunnymodXT.dll'))
ORIGINAL = Path(os.environ.get('MC_ORIGINAL_DLL', HERE.parent / 'upload/BunnymodXT(1).dll'))

def bsp(entities, version=30):
    body = entities.encode('ascii') + b'\0'
    return struct.pack('<III', version, 124, len(body)) + bytes(112) + body

class Engine:
    TABLE = 0x70000000
    FUNCS = 0x70001000
    STRINGS = 0x70002000
    FILE = 0x70100000
    STACK = 0x71000000
    STOP = 0x72000000

    def __init__(self, base=0x10000000):
        self.base = base
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        pe = pefile.PE(str(DLL))
        pe.relocate_image(base)
        self.uc.mem_map(base, pe.OPTIONAL_HEADER.SizeOfImage)
        self.uc.mem_write(base, bytes(pe.header))
        for s in pe.sections:
            self.uc.mem_write(base + s.VirtualAddress, bytes(s.get_data()))
        self.uc.mem_map(self.TABLE, 0x200000)
        self.uc.mem_map(self.STACK, 0x10000)
        self.uc.mem_map(self.STOP, 0x1000)
        self.uc.reg_write(UC_X86_REG_FPCW, 0x37f)
        self.write32(base + 0x13d91cc0, self.TABLE)
        self.angles = [17.5, 12.5, -4.25]
        self.sets, self.loads, self.frees = [], [], []
        self.messages, self.registered = [], []
        self.maxclients = 1
        self.map = 'maps/c1a0.bsp'
        self.dir = 'valve'
        self.file = bsp('{"classname" "worldspawn"}\n{"classname" "info_player_start" "angles" "0 90 0"}')
        self.handlers = {}
        for i, callback in [(30,self.print), (34,self.get_angles), (35,self.set_angles),
                            (36,self.clients), (40,self.printf), (71,self.gamedir),
                            (74,self.level), (79,self.load), (81,self.free)]:
            addr = self.FUNCS + i * 16
            self.write32(self.TABLE + 4*i, addr)
            self.uc.mem_write(addr, b'\xc3')
            self.handlers[addr] = callback
        self.uc.mem_write(base + 0xc0de0, b'\xc3')
        self.handlers[base + 0xc0de0] = self.add
        self.uc.hook_add(UC_HOOK_CODE, self.hook)

    def write32(self, addr, value): self.uc.mem_write(addr, struct.pack('<I',value))
    def read32(self, addr): return struct.unpack('<I',self.uc.mem_read(addr,4))[0]
    def arg(self, i): return self.read32(self.uc.reg_read(UC_X86_REG_ESP) + 4 + i*4)
    def cstr(self, addr):
        out = bytearray()
        for i in range(8192):
            b = self.uc.mem_read(addr+i,1)[0]
            if not b: return out.decode('ascii')
            out.append(b)
        raise AssertionError('Unterminated string')
    def hook(self, uc, addr, size, user):
        if addr in self.handlers: self.handlers[addr]()
    def ret(self, n): self.uc.reg_write(UC_X86_REG_EAX,n)
    def print(self): self.messages.append(self.cstr(self.arg(0)))
    def printf(self): self.messages.append(self.cstr(self.arg(0)))
    def get_angles(self): self.uc.mem_write(self.arg(0),struct.pack('<3f',*self.angles))
    def set_angles(self):
        self.angles = list(struct.unpack('<3f',self.uc.mem_read(self.arg(0),12)))
        self.sets.append(self.angles[:])
    def clients(self): self.ret(self.maxclients)
    def level(self):
        self.uc.mem_write(self.STRINGS,self.map.encode()+b'\0'); self.ret(self.STRINGS)
    def gamedir(self):
        self.uc.mem_write(self.STRINGS+512,self.dir.encode()+b'\0'); self.ret(self.STRINGS+512)
    def load(self):
        self.loads.append((self.cstr(self.arg(0)),self.arg(1)))
        if self.file is None: self.ret(0); return
        self.uc.mem_write(self.FILE,self.file)
        self.write32(self.arg(2),len(self.file)); self.ret(self.FILE)
    def free(self): self.frees.append(self.arg(0))
    def add(self):
        self.registered.append((self.cstr(self.uc.reg_read(UC_X86_REG_ECX)),self.uc.reg_read(UC_X86_REG_EDX)))
    def call(self, name, args=(), ecx=0, edx=0, raw=None):
        stack = self.STACK + 0xf000
        self.uc.mem_write(stack,struct.pack('<%dI'%(1+len(args)),self.STOP,*args))
        self.uc.reg_write(UC_X86_REG_ESP,stack)
        self.uc.reg_write(UC_X86_REG_ECX,ecx)
        self.uc.reg_write(UC_X86_REG_EDX,edx)
        preserve = {UC_X86_REG_EBX:0x1234abcd,UC_X86_REG_ESI:0x24681357,
                    UC_X86_REG_EDI:0x87654321,UC_X86_REG_EBP:0x13572468}
        for r,v in preserve.items(): self.uc.reg_write(r,v)
        addr = raw if raw is not None else self.base + META['symbols'][name]
        self.uc.emu_start(addr,self.STOP,count=1000000)
        assert self.uc.reg_read(UC_X86_REG_EIP)==self.STOP,'Instruction limit / unexpected return'
        assert self.uc.reg_read(UC_X86_REG_ESP)==stack+4,'Stack unbalanced'
        for r,v in preserve.items(): assert self.uc.reg_read(r)==v,'Callee-saved register corrupted'
        assert self.uc.reg_read(UC_X86_REG_FPCW)==0x37f,'Floating point control word changed'
        return self.uc.reg_read(UC_X86_REG_EAX)

class Tests(unittest.TestCase):
    def test_original_preserved(self):
        a,b = pefile.PE(str(ORIGINAL)),pefile.PE(str(DLL))
        for i,s in enumerate(a.sections):
            old,new = s.get_data(),b.sections[i].get_data()
            diffs=[k for k,(x,y) in enumerate(zip(old,new)) if x!=y]
            if i==0:
                self.assertTrue(diffs)
                self.assertTrue(all(0xd57c0-s.VirtualAddress<=k<0xd57c5-s.VirtualAddress for k in diffs))
            else: self.assertEqual(old,new)
        self.assertEqual(a.OPTIONAL_HEADER.AddressOfEntryPoint,b.OPTIONAL_HEADER.AddressOfEntryPoint)
        self.assertEqual(a.OPTIONAL_HEADER.DllCharacteristics,b.OPTIONAL_HEADER.DllCharacteristics)
        for i,(x,y) in enumerate(zip(a.OPTIONAL_HEADER.DATA_DIRECTORY,b.OPTIONAL_HEADER.DATA_DIRECTORY)):
            if i!=5:self.assertEqual((x.VirtualAddress,x.Size),(y.VirtualAddress,y.Size))
        self.assertEqual([(x.name,x.address) for x in a.DIRECTORY_ENTRY_EXPORT.symbols],
                         [(x.name,x.address) for x in b.DIRECTORY_ENTRY_EXPORT.symbols])
        rel_a={(r.rva,r.type) for block in a.DIRECTORY_ENTRY_BASERELOC for r in block.entries if r.type}
        rel_b={(r.rva,r.type) for block in b.DIRECTORY_ENTRY_BASERELOC for r in block.entries if r.type}
        self.assertTrue(rel_a<rel_b)
        self.assertEqual(b.OPTIONAL_HEADER.CheckSum,b.generate_checksum())
        self.assertEqual(b.OPTIONAL_HEADER.SizeOfImage%4096,0)
        self.assertTrue(all(not(s.Characteristics & 0x20000000 and s.Characteristics & 0x80000000) for s in b.sections))

    def test_actual_call_and_aslr(self):
        for base in (0x10000000,0x38000000,0x04000000):
            with self.subTest(base=hex(base)):
                e=Engine(base)
                # Execute the original mov/mov/call sequence; stop immediately after CALL.
                continuation=base+0xd57c5
                e.uc.mem_write(continuation,b'\xc3')
                e.call('',raw=base+0xd57b6)
                self.assertEqual([x[0] for x in e.registered],['bxt_set_angles','mariocam_left','mariocam_right','mariocam_reset','mariocam_info'])
                self.assertEqual(e.registered[0][1],base+0xeb610)
                e.call('mc_left');self.assertEqual(e.angles,[17.5,57.5,-4.25])
                e.call('mc_right');self.assertEqual(e.angles,[17.5,12.5,-4.25])
                for _ in range(8):e.call('mc_left')
                self.assertEqual(e.angles,[17.5,12.5,-4.25])
                for _ in range(8):e.call('mc_right')
                self.assertEqual(e.angles,[17.5,12.5,-4.25])
                e.call('mc_reset');self.assertEqual(e.angles,[0,90,0])
                self.assertEqual(e.loads,[('maps/c1a0.bsp',5)])
                self.assertEqual(len(e.frees),1)

    def test_wrap_pitch_roll_and_controls(self):
        e=Engine()
        for yaw,cmd,want in [(350,'mc_left',35),(10,'mc_right',325),(-170,'mc_right',145),(720,'mc_left',45)]:
            e.angles=[-42.25,yaw,5.5];e.call(cmd)
            self.assertEqual(e.angles,[-42.25,want,5.5])
        e.maxclients=2;n=len(e.sets);e.call('mc_left');self.assertEqual(len(e.sets),n)
        e.maxclients=1;e.map='';e.call('mc_reset');self.assertEqual(len(e.sets),n)
        e.map='maps/c1a0.bsp';e.angles=[0,float('nan'),0];e.call('mc_left');self.assertEqual(len(e.sets),n)
        e.write32(e.base+0x13d91cc0,0);e.call('mc_left');self.assertEqual(len(e.sets),n)

    def test_reset_across_maps_and_mod_switch(self):
        e=Engine();e.map='maps/c4a3.bsp'
        e.file=bsp('{"angle" "270" "classname" "info_player_start"}')
        e.call('mc_reset');self.assertEqual(e.angles,[0,270,0])
        for name in ['maps/c1a1.bsp','maps/c2a5.bsp','maps/c4a3.bsp']:
            e.map=name;e.angles=[-35,22,16];e.call('mc_reset')
            self.assertEqual(e.angles,[0,270,0])
        self.assertEqual(len(e.loads),1)
        e.dir='Blindfolded';e.file=bsp('{"classname" "info_player_start" "angles" "-10 135 2"}')
        e.call('mc_reset');self.assertEqual(e.angles,[-10,135,2]);self.assertEqual(len(e.loads),2)
        replacement=e.TABLE+0x400
        e.uc.mem_write(replacement,bytes(e.uc.mem_read(e.TABLE,82*4)))
        e.write32(e.base+0x13d91cc0,replacement)
        e.call('mc_reset');self.assertEqual(e.angles,[-10,135,2]);self.assertEqual(len(e.loads),3)
        e.call('mc_info');self.assertTrue(any('EXPERIMENTAL' in s for s in e.messages))

    def test_bad_map_leaves_view_unchanged(self):
        e=Engine()
        cases=[None,b'',b'not a BSP',bsp('{"classname" "worldspawn"}'),
               bsp('{"classname" "info_player_start" "angle" "nan"}'),
               bsp('{"classname" "info_player_start" "angles" "0 90"}'),
               bsp('{"classname" "info_player_start" "angle" "90"'),
               bsp('{"classname" "info_player_start"}',version=29)]
        for f in cases:
            with self.subTest(data=f):
                e.file=f;e.call('mc_reset');self.assertEqual(e.angles,[17.5,12.5,-4.25])
        self.assertEqual(len(e.sets),0)
        self.assertEqual(len(e.frees),len(cases)-1)
        self.assertTrue(any('view unchanged' in s for s in e.messages))

    def test_parser_on_actual_x86(self):
        e=Engine();out=e.STRINGS+1024
        cases=[('{"classname" "info_player_start"}',[0,0,0]),
          ('// comment\n{ "wad" "'+'x'*2000+'" "classname" "worldspawn"}\n{"angles" "-2.5 1.35e2 +3.25" "classname" "info_player_start"}',[-2.5,135,3.25]),
          ('{"classname" "info_player_start" "angle" "-1"}',[-90,0,0]),
          ('{"classname" "info_player_start" "angle" "-2"}',[90,0,0]),
          ('{"classname" "info_player_start" "angle" "90"}{"classname" "info_player_start" "angle" "180"}',[0,90,0])]
        for entities,want in cases:
            f=bsp(entities);e.uc.mem_write(e.FILE,f)
            self.assertEqual(e.call('mc_find_spawn',(e.FILE,len(f),out)),1)
            self.assertEqual(list(struct.unpack('<3f',e.uc.mem_read(out,12))),want)
        for offset,length in [(0,5),(0xffffffff,5),(124,0xffffffff)]:
            f=struct.pack('<III',30,offset,length)+bytes(112)
            e.uc.mem_write(e.FILE,f)
            self.assertEqual(e.call('mc_find_spawn',(e.FILE,len(f),out)),0)

if __name__=='__main__': unittest.main(verbosity=2)
