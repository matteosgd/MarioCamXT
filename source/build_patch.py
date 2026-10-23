#!/usr/bin/env python3
"""Build a minimal extension for one hash-verified BunnymodXT DLL.

Requires Python 3, pefile, pyelftools, GCC with -m32 compilation, GNU ld/objdump.
No 32-bit libc or Windows SDK is needed: the extension is freestanding C.
Original BXT code changes: one five-byte relative CALL at RVA 0x000d57c0.
All original commands, exports, entry point, imports, TLS, and data are retained.
The extension calls the original registration function before adding its commands.
"""
from pathlib import Path
import argparse, hashlib, json, struct, subprocess
import pefile
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection

BASE = 0x10000000
SOURCE_SHA = '34618c2273b38b1f4690c1feef8aa00f32c7f5bf3765f7f0bbb7a303feb60840'
CALL_RVA = 0x000d57c0
CALL_BYTES = bytes.fromhex('e8 1b b6 fe ff')
HERE = Path(__file__).resolve().parent

def align(n, a): return (n + a - 1) // a * a
def run(args): subprocess.run([str(x) for x in args], check=True, capture_output=True, text=True)

def build(source, output, work):
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA:
        raise ValueError('Input is not the exact supported nov-11-2024 HL BXT DLL. Nothing patched.')
    pe = pefile.PE(data=original)
    assert pe.FILE_HEADER.Machine == 0x14c and pe.OPTIONAL_HEADER.ImageBase == BASE
    assert pe.get_data(CALL_RVA, 5) == CALL_BYTES
    work.mkdir(parents=True, exist_ok=True)
    start = align(pe.OPTIONAL_HEADER.SizeOfImage, 0x1000)
    linker = work / 'extension.ld'
    linker.write_text('''SECTIONS {
  . = 0x%x;
  .mc_code : { *(.text*) *(.rodata*) }
  . = ALIGN(4096);
  .mc_data : { *(.data*) *(.bss*) *(COMMON) BYTE(0); }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
_ImageBase = 0x10000000;
''' % (BASE + start))
    obj, elf = work / 'extension.o', work / 'extension.elf'
    run(['gcc', '-m32', '-march=i686', '-Os', '-std=c99', '-Wall', '-Wextra', '-Werror',
         '-ffreestanding', '-fno-pic', '-fno-pie', '-fno-stack-protector',
         '-fno-builtin', '-fno-asynchronous-unwind-tables', '-fno-unwind-tables',
         '-fno-common', '-fno-merge-constants', '-mno-sse', '-mno-mmx',
         '-mpreferred-stack-boundary=2', '-mincoming-stack-boundary=2',
         '-c', HERE / 'mariocam.c', '-o', obj])
    run(['ld', '-m', 'elf_i386', '-T', linker, '--emit-relocs', '-e', 'mc_register', '-o', elf, obj])
    new_sections = []
    new_relocs = []
    with elf.open('rb') as f:
        el = ELFFile(f)
        symtab = el.get_section_by_name('.symtab')
        symbols = {s.name: s['st_value'] - BASE for s in symtab.iter_symbols()
                   if s.name and s['st_value'] >= BASE}
        for name, flags in [('.mc_code', 0x60000020), ('.mc_data', 0xc0000040)]:
            sec = el.get_section_by_name(name)
            new_sections.append((name, sec['sh_addr'] - BASE, sec.data(), flags))
        for sec in el.iter_sections():
            if isinstance(sec, RelocationSection):
                for r in sec.iter_relocations():
                    if r['r_info_type'] == 1:  # R_386_32 => IMAGE_REL_BASED_HIGHLOW
                        new_relocs.append(r['r_offset'] - BASE)
                    elif r['r_info_type'] != 2:  # R_386_PC32 is position-independent
                        raise ValueError('Unexpected ELF relocation: %r' % r.entry)
        assert not [s.name for s in symtab.iter_symbols()
                    if s.name and s['st_shndx'] == 'SHN_UNDEF'], 'Unresolved import'
    # Keep every original relocation, adding relocations for new absolute pointers.
    entries = [(r.rva, r.type) for block in pe.DIRECTORY_ENTRY_BASERELOC
               for r in block.entries if r.type]
    entries += [(r, 3) for r in new_relocs]
    assert len(entries) == len(set(entries)), 'Duplicate relocation'
    pages = {}
    for rva, typ in sorted(entries): pages.setdefault(rva & ~0xfff, []).append((typ << 12) | (rva & 0xfff))
    reloc_data = bytearray()
    for page, values in sorted(pages.items()):
        if len(values) % 2: values.append(0)
        reloc_data += struct.pack('<II', page, 8 + 2 * len(values))
        reloc_data += struct.pack('<%dH' % len(values), *values)
    last = new_sections[-1]
    reloc_rva = align(last[1] + len(last[2]), 0x1000)
    new_sections.append(('.mc_relo', reloc_rva, bytes(reloc_data), 0x42000040))
    first_header = pe.sections[0].get_file_offset()
    count = len(pe.sections)
    assert first_header + 40 * (count + len(new_sections)) <= pe.OPTIONAL_HEADER.SizeOfHeaders
    result = bytearray(original)
    for i, (name, rva, content, flags) in enumerate(new_sections):
        offset = align(len(result), pe.OPTIONAL_HEADER.FileAlignment)
        raw_size = align(len(content), pe.OPTIONAL_HEADER.FileAlignment)
        result.extend(bytes(offset - len(result)))
        result.extend(content)
        result.extend(bytes(raw_size - len(content)))
        struct.pack_into('<8sIIIIIIHHI', result, first_header + (count + i) * 40,
                         name.encode(), len(content), rva, raw_size, offset, 0, 0, 0, 0, flags)
    def set_field(structure, name, value, fmt='<I'):
        struct.pack_into(fmt, result, structure.get_field_absolute_offset(name), value)
    set_field(pe.FILE_HEADER, 'NumberOfSections', count + len(new_sections), '<H')
    set_field(pe.OPTIONAL_HEADER, 'SizeOfImage', align(reloc_rva + len(reloc_data), 0x1000))
    set_field(pe.OPTIONAL_HEADER, 'SizeOfCode', pe.OPTIONAL_HEADER.SizeOfCode + align(len(new_sections[0][2]), 512))
    set_field(pe.OPTIONAL_HEADER, 'SizeOfInitializedData', pe.OPTIONAL_HEADER.SizeOfInitializedData
              + sum(align(len(x[2]), 512) for x in new_sections[1:]))
    relocdir = pe.OPTIONAL_HEADER.DATA_DIRECTORY[5]
    set_field(relocdir, 'VirtualAddress', reloc_rva)
    set_field(relocdir, 'Size', len(reloc_data))
    call_off = pe.get_offset_from_rva(CALL_RVA)
    result[call_off:call_off + 5] = b'\xe8' + struct.pack('<i', symbols['mc_register'] - CALL_RVA - 5)
    # A correct checksum is optional for a user-mode DLL, but makes inspection clear.
    set_field(pe.OPTIONAL_HEADER, 'CheckSum', 0)
    checksum = pefile.PE(data=result).generate_checksum()
    set_field(pe.OPTIONAL_HEADER, 'CheckSum', checksum)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    metadata = {
        'version': 'MarioCam XT 0.1 experimental', 'source_commit': 'cbc496b1ba7f6c242a961c33f16d3b5741371dd6',
        'source_sha256': SOURCE_SHA, 'output_sha256': hashlib.sha256(result).hexdigest(),
        'base': BASE, 'patched_call_rva': CALL_RVA, 'symbols': symbols,
        'new_relocations': len(new_relocs), 'total_relocations': len(entries),
    }
    (work / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({k: v for k, v in metadata.items() if k != 'symbols'}, indent=2))
    return metadata

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('original_dll', type=Path)
    p.add_argument('output_dll', type=Path)
    p.add_argument('--work', type=Path, default=HERE / 'build')
    a = p.parse_args()
    build(a.original_dll, a.output_dll, a.work)
