#!/usr/bin/python
from elftools.elf.elffile import ELFFile
import capstone
import sys
#import cProfile
import x64_assembler
import bin_write
import json
import os
import re

from context import Context
from brute_force_mapper import BruteForceMapper

save_reg_template = '''
mov DWORD PTR [esp%s], %s
'''
restore_reg_template = '''
mov %s, DWORD PTR [esp%s]
'''

save_register = '''
mov %s, -12
mov %s, %s'''

memory_ref_string = re.compile(u'^dword ptr \[(?P<address>0x[0-9a-z]+)\]$')

'''
call X
'''#%('eax',cs_insn.reg_name(opnd.reg),'eax')
'''
class Context(object):
  def __init__():
    self'''

#Transforms the 'r_info' field in a relocation entry to the offset into another table
#determined by the host reloc table's 'sh_link' entry.  In our case it's the dynsym table.
def ELF32_R_SYM(val):
  return (val) >> 8
def ELF64_R_SYM(val):
  return (val) >> 32

#Globals: If there end up being too many of these, put them in a Context & pass them around
'''plt = {}
newbase = 0x09000000
#TODO: Set actual address of function
lookup_function_offset = 0x8f
secondary_lookup_function_offset = 0x8f #ONLY used when rewriting ONLY main executable
mapping_offset = 0x8f
global_sysinfo = 0x8f	#Address containing sysinfo's address
global_flag = 0x8f
global_lookup = 0x7000000	#Address containing global lookup function
popgm = 'popgm'
popgm_offset = 0x8f
new_entry_off = 0x8f
write_so = False
exec_only = False
no_pic = False
get_pc_thunk = None
stat = {}
stat['indcall'] = 0
stat['indjmp'] = 0
stat['dircall'] = 0
stat['dirjmp'] = 0
stat['jcc'] = 0
stat['ret'] = 0
stat['origtext'] = 0
stat['newtext'] = 0
stat['origfile'] = 0
stat['newfile'] = 0
stat['mapsize'] = 0
stat['lookupsize'] = 0
#stat['auxvecsize'] = 0
#stat['globmapsize'] = 0
#stat['globlookupsize'] = 0
#List of library functions that have callback args; each function in the dict has a list of
#the arguments passed to it that are a callback (measured as the index of which argument it is)
#TODO: Handle more complex x64 calling convention
#TODO: Should I count _rtlf_fini (offset 5)?  It seems to be not in the binary
callbacks = {'__libc_start_main':[0,3,4]}'''

class Rewriter(object):

  def __init__(self,write_so,exec_only,no_pic):
    self.context = Context()
    self.context.write_so = write_so
    self.context.exec_only = exec_only
    self.context.no_pic = no_pic

  def set_before_inst_callback(self,func):
    '''Pass a function that will be called when translating each instruction.
       This function should accept an instruction argument (the instruction type returned from capstone),
       which can be read to determine what code to insert (if any).  A byte string of assembled bytes
       should be returned to be inserted before the instruction, or if none are to be inserted, return None.
  
       NOTE: NOTHING is done to protect the stack, registers, flags, etc!  If ANY of these are changed, there
       is a chance that EVERYTHING will go wrong!  Leave everything as you found it or suffer the consequences!
    '''
    self.context.before_inst_callback = func

  def alloc_globals(self,size,arch):
    '''Allocate an arbitrary amount of contiguous space for global variables for use by instrumentation code.
       Returns the address of the start of this space.
    '''
    #create a temporary mapper to get where the globals would be inserted
    self.context.alloc_globals = 0
    mapper = BruteForceMapper(arch,b'',0,0,self.context)#hz-
    retval = self.context.global_lookup + len(mapper.runtime.get_global_mapping_bytes())
    #Now actually set the size of allocated space
    self.context.alloc_globals = size
    return retval
  
  #Find the earliest address we can place the new code
  def find_newbase(self,elffile):
    maxaddr = 0
    for seg in elffile.iter_segments():
      segend = seg.header['p_vaddr']+seg.header['p_memsz']
      if segend > maxaddr:
        maxaddr = segend
    maxaddr += ( 0x1000 - maxaddr%0x1000 ) # Align to page boundary
    return maxaddr

  def rewrite(self,fname,arch):
    offs = size = addr = 0
    with open(fname,'rb') as f:
      elffile = ELFFile(f)
      relplt = None
      relaplt = None
      dynsym = None
      entry = elffile.header.e_entry #application entry point
      for section in elffile.iter_sections():
        if section.name == '.text':
          print "Found .text"
          offs = section.header.sh_offset
          size = section.header.sh_size
          addr = section.header.sh_addr
          self.context.oldbase = addr
          # If .text section is large enough to hold all new segments, we can move the phdrs there
          if size >= elffile.header['e_phentsize']*(elffile.header['e_phnum']+self.context.num_new_segments+1):
            self.context.move_phdrs_to_text = True
        if section.name == '.plt':
          self.context.plt['addr'] = section.header['sh_addr']
          self.context.plt['size'] = section.header['sh_size']
          self.context.plt['data'] = section.data()
        if section.name == '.rel.plt':
          relplt = section
        if section.name == '.rela.plt': #x64 has .rela.plt
          relaplt = section
        if section.name == '.dynsym':
          dynsym = section
        if section.name == '.symtab':
          for sym in section.iter_symbols():
            if sym.name == '__x86.get_pc_thunk.bx':
              self.context.get_pc_thunk = sym.entry['st_value'] #Address of thunk
          #section.get_symbol_by_name('__x86.get_pc_thunk.bx')) #Apparently this is in a newer pyelftools
      self.context.plt['entries'] = {}
      if relplt is not None:
        for rel in relplt.iter_relocations():
          got_off = rel['r_offset'] #Get GOT offset address for this entry
          ds_ent = ELF32_R_SYM(rel['r_info']) #Get offset into dynamic symbol table
          if dynsym:
            name = dynsym.get_symbol(ds_ent).name #Get name of symbol
            self.context.plt['entries'][got_off] = name #Insert this mapping from GOT offset address to symbol name
      elif relaplt is not None:
        for rel in relaplt.iter_relocations():
          got_off = rel['r_offset'] #Get GOT offset address for this entry
          ds_ent = ELF64_R_SYM(rel['r_info']) #Get offset into dynamic symbol table
          if dynsym:
            name = dynsym.get_symbol(ds_ent).name #Get name of symbol
            self.context.plt['entries'][got_off] = name #Insert this mapping from GOT offset address to symbol name
        #print self.context.plt
      else:
          print 'binary does not contain plt'
      if self.context.write_so:
        print 'Writing as .so file'
        self.context.newbase = self.find_newbase(elffile)
      elif self.context.exec_only:
        print 'Writing ONLY main binary, without support for rewritten .so files'
        self.context.newbase = 0x09000000
      else:
        print 'Writing as main binary'
        self.context.newbase = 0x09000000
      if self.context.no_pic:
        print 'Rewriting without support for generic PIC'
      for seg in elffile.iter_segments():
        if seg.header['p_flags'] == 5 and seg.header['p_type'] == 'PT_LOAD': #Executable load seg
          print "Base address: %s"%hex(seg.header['p_vaddr'])
          bytes = seg.data()
          base = seg.header['p_vaddr']
          mapper = BruteForceMapper(arch,bytes,base,entry,self.context)#hz-
          mapping = mapper.gen_mapping()
          newbytes = mapper.gen_newcode(mapping)
          #Perhaps I could find a better location to set the value of global_flag
          #(which is the offset from gs)
          #I only need one byte for the global flag, so I am adding a tiny bit to TLS
          #add_tls_section returns the offset, but we must make it negative
          self.context.global_flag = -bin_write.add_tls_section(fname,b'\0')
          print 'just set global_flag value to 0x%x'%self.context.global_flag
          #maptext = write_mapping(mapping,base,len(bytes))
          #(mapping,newbytes) = translate_all(seg.data(),seg.header['p_vaddr'])
          #insts = md.disasm(newbytes[0x8048360-seg.header['p_vaddr']:0x8048441-seg.header['p_vaddr']],0x8048360)
          #The "mysterious" bytes between the previously patched instruction 
          #(originally at 0x804830b) are the remaining bytes from that jmp instruction!
          #So even though there was nothing between that jmp at the end of that plt entry
          #and the start of the next plt entry, now there are 4 bytes from the rest of the jmp.
          #This is a good example of why I need to take a different approach to generating the mapping.
          #insts = md.disasm(newbytes[0x80483af-seg.header['p_vaddr']:0x80483bf-seg.header['p_vaddr']],0x80483af)
          #insts = md.disasm(newbytes,0x8048000)
          #for ins in insts:
          #  print '0x%x:\t%s\t%s'%(ins.address,ins.mnemonic,ins.op_str)
          #tmpdct = {hex(k): (lambda x:hex(x+seg.header['p_vaddr']))(v) for k,v in mapping.items()}
          #keys = tmpdct.keys()
          #keys.sort()
          #output = ''
          #for key in keys:
          #  output+='%s:%s '%(key,tmpdct[key])
          with open('newbytes','wb') as f2:
            f2.write(newbytes)
          if not self.context.write_so:
            with open('newglobal','wb') as f2:
              f2.write(mapper.runtime.get_global_mapping_bytes())
          #print output
          print mapping[base]
          print mapping[base+1]
          maptext = mapper.write_mapping(mapping,base,len(bytes))
          cache = ''
          for x in maptext:
            #print x
            cache+='%d,'%int(x.encode('hex'),16)
          #print cache
  	  #print maptext.encode('hex')
          print '0x%x'%(base+len(bytes))
  	  print 'code increase: %d%%'%(((len(newbytes)-len(bytes))/float(len(bytes)))*100)
          lookup = mapper.runtime.get_lookup_code(base,len(bytes),self.context.lookup_function_offset,0x8f)
          print 'lookup w/unknown mapping %s'%len(lookup)
          #insts = md.disasm(lookup,0x0)
  	  #for ins in insts:
          #  print '0x%x:\t%s\t%s\t%s'%(ins.address,str(ins.bytes).encode('hex'),ins.mnemonic,ins.op_str)
          lookup = mapper.runtime.get_lookup_code(base,len(bytes),self.context.lookup_function_offset,mapping[self.context.mapping_offset])
          print 'lookup w/known mapping %s'%len(lookup)
          #insts = md.disasm(lookup,0x0)
  	  #for ins in insts:
          #  print '0x%x:\t%s\t%s\t%s'%(ins.address,str(ins.bytes).encode('hex'),ins.mnemonic,ins.op_str)
          if not self.context.write_so:
            print 'new entry point: 0x%x'%(self.context.newbase + self.context.new_entry_off)
            print 'new _start point: 0x%x'%(self.context.newbase + mapping[entry])
            print 'global lookup: 0x%x'%self.context.global_lookup
          print 'local lookup: 0x%x'%self.context.lookup_function_offset
          print 'secondary local lookup: 0x%x'%self.context.secondary_lookup_function_offset
          print 'mapping offset: 0x%x'%mapping[self.context.mapping_offset]
          with open('%s-r-map.json'%fname,'wb') as f:
            json.dump(mapping,f)
          if not self.context.write_so:
            bin_write.rewrite(fname,fname+'-r','newbytes',self.context.newbase,mapper.runtime.get_global_mapping_bytes(),self.context.global_lookup,self.context.newbase+self.context.new_entry_off,offs,size,self.context.num_new_segments,arch)
          else:
            self.context.new_entry_off = mapping[entry]
            bin_write.rewrite_noglobal(fname,fname+'-r','newbytes',self.context.newbase,self.context.newbase+self.context.new_entry_off)
          self.context.stat['origtext'] = len(bytes)
          self.context.stat['newtext'] = len(newbytes)
          self.context.stat['origfile'] = os.path.getsize(fname)
          self.context.stat['newfile'] = os.path.getsize(fname+'-r')
          self.context.stat['mapsize'] = len(maptext)
          self.context.stat['lookupsize'] = \
            len(mapper.runtime.get_lookup_code(base,len(bytes),self.context.lookup_function_offset,mapping[self.context.mapping_offset]))
          if self.context.exec_only:
            self.context.stat['secondarylookupsize'] = \
              len(mapper.runtime.get_secondary_lookup_code(base,len(bytes), \
                self.context.secondary_lookup_function_offset,mapping[self.context.mapping_offset]))
          if not self.context.write_so:
            self.context.stat['auxvecsize'] = len(mapper.runtime.get_auxvec_code(mapping[entry]))
            popgm = 'x86_popgm' if arch == 'x86' else 'x64_popgm' # TODO: if other architectures are added, this will need to be changed
            with open(os.path.dirname(os.path.realpath(sys.argv[0])) + os.sep + popgm) as f:
            # with open(popgm) as f:
              tmp=f.read()
              self.context.stat['popgmsize'] = len(tmp)
            self.context.stat['globmapsectionsize'] = len(mapper.runtime.get_global_mapping_bytes())
            self.context.stat['globlookupsize'] = len(mapper.runtime.get_global_lookup_code())
          with open('%s-r-stat.json'%fname,'wb') as f:
            json.dump(self.context.stat,f,sort_keys=True,indent=4,separators=(',',': '))
          
'''
  with open(fname,'rb') as f:
    f.read(offs)
    bytes = f.read(size)
    (mapping,newbytes) = translate_all(bytes,addr)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for i in range(0,size):
      #print dir(md.disasm(bytes[i:i+15],addr+i))
      insts = md.disasm(newbytes[i:i+15],addr+i)
      ins = None
      try:
        ins = insts.next()#longest possible x86/x64 instruction is 15 bytes
        #print str(ins.bytes).encode('hex')
        #print ins.size
        #print dir(ins)
      except StopIteration:
        pass
      if ins is None:
        pass#print 'no legal decoding'
      else:
      	pass#print '0x%x:\t%s\t%s'%(ins.address,ins.mnemonic,ins.op_str)
    print {k: (lambda x:x+addr)(v) for k,v in mapping.items()}
    print asm(save_register%('eax','eax','eax')).encode('hex')'''
    
if __name__ == '__main__':
  import argparse

  parser = argparse.ArgumentParser(description='''Rewrite a binary so that the code is relocated.
Running this script from the terminal does not allow any instrumentation.
For that, use this as a library instead.''')
  parser.add_argument('filename',help='The executable file to rewrite.')
  parser.add_argument('--so',action='store_true',help='Write a shared object.')
  parser.add_argument('--execonly',action='store_true',help='Write only a main executable without .so support.')
  parser.add_argument('--nopic',action='store_true',help='Write binary without support for arbitrary pic.  It still supports common compiler-generated pic.')
  parser.add_argument('--arch',default='x86',help='The architecture of the binary.  Default is \'x86\'.')
  args = parser.parse_args()
  rewriter = Rewriter(args.so,args.execonly,args.nopic)
  rewriter.rewrite(args.filename,args.arch)
  #cProfile.run('renable(args.filename,args.arch)')

