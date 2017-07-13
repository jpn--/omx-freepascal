# Generate Delphi wrapper for HDF5 library.
# by Andrey Paramonov

from __future__ import print_function

import sys
import os.path
import argparse
import networkx as nx
import datetime
import re
from collections import *
from itertools import *

parser = argparse.ArgumentParser(description = 'Generate Delphi wrapper for HDF5 library.')
parser.add_argument('srcdir', help = 'directory containing HDF5 *.h files.',
                    nargs = '?', default = '.')
args = parser.parse_args()

def parsedeps(header, graph):
    if header.startswith('H5') and header not in graph.onodes:
        graph.onodes.append(header)
    for line in open(os.path.join(args.srcdir, header)):
        m = re.match('#include "(H5.*public.h)".*', line)
        if m:
            include = m.group(1)
            if header.startswith('H5'):
                if include not in graph.onodes:
                    graph.onodes.append(include)
                graph.add_edge(header, include)
            parsedeps(include, graph)

defs = ''
classname = 'THDF5Dll'
types = ''
fields = ''
props = ''
init = ''
cinit = ''

template = \
'''unit hdf5dll;

// Delphi wrapper for HDF5 library.

// Auto-generated {date} by hdf5pas.py.

interface

uses
  windows;

{{$ALIGN ON}}
{{$MINENUMSIZE 4}}

type
  int32_t = Integer;
  Pint32_t = ^int32_t;
  uint32_t = Cardinal;
  Puint32_t = ^uint32_t;
  int64_t = Int64;
  Pint64_t = ^int64_t;
  uint64_t = UInt64;
  Puint64_t = ^uint64_t;
  time_t = NativeInt;
  Ptime_t = ^time_t;
  size_t = NativeUInt;
  Psize_t = ^size_t;
  ssize_t = NativeInt;
  Pssize_t = ^ssize_t;
  off_t = NativeInt;
  Poff_t = ^off_t;
  PFILE = Pointer;

type
  hsize_t = UInt64;
  Phsize_t = ^hsize_t;
  hssize_t = Int64;
  Phssize_t = ^hssize_t;
  haddr_t = UInt64;
  Phaddr_t = ^haddr_t;

const
  HADDR_UNDEF = haddr_t(-1);

{defs}

type
  {classname} = class
  private
  type
{types}

  private
    FHandle: THandle;

{fields}

  public
    constructor Create(APath: string);
    destructor Destroy; override;

{props}

    property Handle: THandle read FHandle;
    function IsValid: Boolean;
  end;

implementation

{{ {classname} }}
constructor {classname}.Create(APath: string);

  function GetDllProc(AModule: THandle; AName: string): Pointer;
  begin
    Result := GetProcAddress(AModule, PChar(AName));
    Assert(Assigned(Result));
  end;

begin
  inherited Create;
  FHandle := LoadLibrary(PChar(APath));

{init}

  H5open;
{cinit}
end;

destructor {classname}.Destroy;
begin
  if FHandle <> 0 then
    FreeLibrary(FHandle);
  inherited;
end;

function {classname}.IsValid: Boolean;
begin
  Result := (FHandle <> 0);
end;

end.
'''

def parse(header):

    def smartjoin(sep, *args):
        if args[0]:
            return sep.join(args)
        else:
            return args[1]

    def stripcomment(s):
        return re.sub(' *(\(\*.*\*\))?$', '', s)

    def strtoint(value):
        value = re.sub('^\(\(.*\)\)$', r'\1', value.strip())
        if value.startswith('('):
            tokens = re.findall('(\((.*?)\)( *|$))|([^()]+$)', value)
            value = (tokens[-1][1] or tokens[-1][3]).strip()
        else:
            tokens = None
        value = value.rstrip('uL')
        try:
            result = int(value, 0)
            if tokens:
                for token in reversed(tokens[:-1]):
                    typ = token[1].strip()
                    (name, typ) = convnametype('', typ)
                    result = '{}({})'.format(typ, result)
        except ValueError:
            m = re.match('(.*) << (.*)', value)
            if m:
                result = '{} shl {}'.format(m.group(1), int(m.group(2), 0))
            else:
                return
        return result

    def strtofloat(value):
        try:
            value = value.rstrip('f')
            return float(value)
        except ValueError:
            pass

    def parseprocdecl(signature, istype):
        signature = re.sub('\(\*[^()]*?\*\)', '', signature).replace('*', ' * ')
        if istype:
            (rettype, name, args) = re.match('(.*) ?\( \* ([^ ]*)\) ?\((.*)\);', signature).groups()
        else:
            (rettype, name, args) = re.match('(.*) ([^ ]*) ?\((.*)\);', signature).groups()
        if args != 'void':
            args = [s.strip() for s in args.split(',')]
        else:
            args = []
        varargs = False
        for i in range(len(args)):
            arg = args[i].strip().split(' ')
            if len([p for p in arg if p != '*']) < 2 and args[i] != '...':
                arg.append('p')
            atyp = ' '.join(arg[:-1])
            aname = arg[-1]
            (aname, atyp) = convnametype(aname, atyp, arraytypes = False)
            if args[i] != '...':
                args[i] = '{}: {}'.format(aname, atyp)
            else:
                args[i] = None
                varargs = True
        args = [s for s in args if s]
        rettype = convnametype('', rettype, arraytypes = False)[-1]
        return name, args, rettype, varargs

    def getnametype(signature):
        while '  ' in signature:
            signature = signature.replace('  ', ' ')
        m = re.match('([^\[\]]*)(\[(.+)\])?', signature.strip())
        lexems = m.group(1).split(' ')
        if lexems[0] == 'enum':
            lexems = lexems[1:]
        arr = m.group(2) or ''
        return lexems[-1] + arr, ' '.join(lexems[:-1])

    def convnametype(cname, ctype, arraytypes = True):
        # Convert C-style variable/constant/field declaration to Delphi-style

        def replace(where, olditems, newitem):
            items = where
            for item in olditems:
                if item in items:
                    items = [s for s in items if s != item]
                else:
                    return where
            return items + [newitem]

        typ = ctype.replace('*', ' * ')
        while '  ' in typ:
            typ = typ.replace('  ', ' ')
        typ = typ.strip().split(' ')
        stars = len([s for s in cname if s == '*'])
        name = cname.strip('* ')
        typ += ['*']*stars
        if name.endswith('[]'):
            name = name.rstrip('[]')
            typ += ['*']
        m = re.match('([^\[\]]*)(\[(.+)\])?', name)
        arrsize = m.group(3)
        name = m.group(1)

        if name == 'type':
            name = 'typ'
        elif name == 'object':
            name = 'obj'
        elif name == 'end':
            name = 'end_'
        elif name == 'file':
            name = 'file_'

        typ = [s for s in typ if s != 'const']
        typ = replace(typ, ['unsigned', 'long', 'long', 'int'], 'UInt64')
        typ = replace(typ, ['unsigned', 'long', 'long'], 'UInt64')
        typ = replace(typ, ['long', 'long', 'int'], 'Int64')
        typ = replace(typ, ['long', 'long'], 'Int64')
        typ = replace(typ, ['unsigned', 'long', 'int'], 'Cardinal')
        typ = replace(typ, ['unsigned', 'long'], 'Cardinal')
        typ = replace(typ, ['long', 'int'], 'Integer')
        typ = replace(typ, ['long'], 'Integer')
        typ = replace(typ, ['unsigned', 'short', 'int'], 'Word')
        typ = replace(typ, ['unsigned', 'short'], 'Word')
        typ = replace(typ, ['short', 'int'], 'ShortInt')
        typ = replace(typ, ['short'], 'ShortInt')
        typ = replace(typ, ['unsigned', 'int'], 'Cardinal')
        typ = replace(typ, ['int'], 'Integer')
        typ = replace(typ, ['unsigned', 'char'], 'Byte')
        typ = replace(typ, ['char'], 'AnsiChar')
        typ = replace(typ, ['unsigned'], 'Cardinal')
        typ = replace(typ, ['bool'], 'Boolean')
        typ = replace(typ, ['double'], 'Double')
        if '*' in typ:
            typ = replace(typ, ['void'], 'ointer')

        stars = len([s for s in typ if s == '*'])
        typ = 'P'*stars + ''.join([s for s in typ if s != '*'])
        if arrsize:
            if arraytypes:
                if arrsize.endswith(' + 1'):
                    typ = 'array[0..{}] of {}'.format(arrsize[0:len(arrsize) - 4], typ)
                else:
                    typ = 'array[0..{} - 1] of {}'.format(arrsize, typ)
            else:
                typ = 'P' + typ
        return (name, typ)

    def preprocess(lines):
        '''
        Parse and strip off pre-processor directives.
        Currently all #if/#ifdef/#ifndef are considered as false.
        '''

        print('{}: Pre-processing...'.format(header), file = sys.stderr)
        ifdef = 0
        result = []
        for line in lines:
            line = line.strip('\n').expandtabs()
            if line.strip() == '':
                line = ''
            m = re.match('(.*)(/\*.*)', line)
            if m and not re.search('\*/', m.group(2)):
                if m.group(1).strip() == '':
                    sublines = [m.group(2)]
                else:
                    sublines = m.groups()
            else:
                sublines = [line]
            for line in sublines:
                line = line.replace('/*', '(*').replace('*/', '*)')
                hdef = '_{}_H'.format(os.path.splitext(header)[0])
                if re.match('#ifndef {}'.format(hdef), line) or \
                   re.match('#define {}'.format(hdef), line):
                    pass
                elif line.startswith('#if') or \
                     line.startswith('#ifdef') or \
                     line.startswith('#ifndef'):
                    ifdef += 1
                elif line.startswith('#endif'):
                    ifdef -= 1
                elif not ifdef:
                    if line.startswith('#include') or line.startswith('#undef'):
                        pass
                    else:
                        result.append(line)
        print('{}: {} of {} lines left'.format(header, len(result), len(lines)), file = sys.stderr)
        return result

    lines = open(os.path.join(args.srcdir, header)).readlines()
    lines = preprocess(lines)

    print('{}: Parsing...'.format(header), file = sys.stderr)

    def process(state, stateinfo, comment):

        def procdefine(lines):
            '''
            Process sequence of #define's.
            '''

            global props

            result = ''
            comment = False
            for line in lines.split('\n'):
                m = re.match(' *?(((\(\*)|( \*)).*)', line)
                if m:
                    comment = True
                    if len(result) > 0:
                        result += '\n' + m.group(1)
                else:
                    m = re.match(r'#define +(.*?) +([^\\]+)$', stripcomment(line))
                    if m:
                        comment = False
                        mm = re.search('\(\*(.*)\*\)', line.strip())
                        comment = mm.group(1) if mm else None
                        (name, value) = m.groups()
                        value = re.sub('^\((.*)\)$', r'\1', value)
                        value = re.sub('^H5CHECK ', '', value)
                        if name.startswith('H5F_ACC_'):
                            value = re.sub('^H5OPEN ', '', value)
                        value = value.replace('sizeof', 'SizeOf')
                        comment = ' '.join(['(*', comment.strip(), '*)'] if comment else '')
                        if '?' in value or ',' in value:
                            print('WARN: {}'.format(line), file = sys.stderr)
                        elif value.startswith('H5OPEN'):
                            props += '    property {}: hid_t read F{};\n'.format(name, value.split(' ')[-1].strip('_g'))
                        elif 'SIZEOF' in name:
                            pass
                        elif strtoint(value) != None:
                            result += '\n  {} = {};  {}'.format(name, strtoint(value), comment)
                        elif strtofloat(value) != None:
                            result += '\n  {} = {};  {}'.format(name, strtofloat(value), comment)
                        elif value.startswith('"') and value.endswith('"'):
                            result += "\n  {} = '{}';  {}".format(name, value.strip('"'), comment)
                        elif len(value.split('|')) > 1:
                            result += '\n  {} = {};  {}'.format(name,
                                                            ' or '.join([item.strip()
                                                                         for item in value.split('|')]),
                                                                comment)
                        elif name.startswith('H5T_INTEL') or \
                             name.startswith('H5T_ALPHA') or \
                             name.startswith('H5T_MIPS'):
                            props += '    property {}: hid_t read F{};\n'.format(name, value)
                        else:
                            result += '\n  {} = {};  {}'.format(name, value, comment)
                    elif comment:
                        result += '\n' + line
                    else:
                        print('WARN: {}'.format(line), file = sys.stderr)
            return result

        def proctypedef(lines):
            '''
            Process sequence of typedefs.
            '''

            def process(prevstate, state, stateinfo):
                '''
                Process one typedef.
                '''

                result = ''

                if len(stateinfo) == 1:
                    if state == 'enum':
                        stateinfo[0] = stateinfo[0].replace('typedef enum', 'typedef')
                    elif state == 'struct':
                        stateinfo[0] = stateinfo[0].replace('typedef struct', 'typedef')
                    state = 'other'

                if state == 'enum':
                    '''
                    Enumerated type declaration.
                    '''

                    result += '\ntype'
                    name = stateinfo[-1].strip('}; ') or stateinfo[0].split(' ')[2]
                    result += '\n  P{name} = ^{name};'.format(name = name)
                    result += '\n  {} ='.format(name)

                    lines = list()
                    Line = namedtuple('Line', ['line', 'name', 'value', 'comment'])
                    lastname = None
                    for line in stateinfo[1:len(stateinfo) - 1]:
                        if stripcomment(line).strip() == '{':
                            continue
                        m = re.match(' *([^ *(),]+)( *= ?([^,]+))?,?', stripcomment(line))
                        if m:
                            (name, dummy, value) = m.groups()
                            value = strtoint(value) if value else None
                            mm = re.search('\(\*(.*)\*\)', line.strip())
                            comment = mm.group(1) if mm else None
                            comment = ' '.join(['(*', comment.strip(), '*)'] if comment else '')
                            lines.append(Line(line = None, name = name, value = value, comment = comment))
                            lastname = name
                        elif not stripcomment(line).strip():
                            lines.append(Line(line = line.strip(), name = None, value = None, comment = None))
                        elif re.match(' *([( ]\*.*)', line):
                            lines.append(Line(line = re.sub(' *([( ]\*.*)', r'\1', line), name = None, value = None, comment = None))
                        else:
                            print('WARN: {}'.format(line), file = sys.stderr)
                    firstline = True
                    for line in lines:
                        if line.line != None:
                            result += '\n' + line.line
                        else:
                            result += '\n    {}{}{}{}  {}'.format(
                                '(' if firstline else ' ', line.name, ' = {}'.format(line.value) if line.value else '',
                                ');' if line.name == lastname else ',', line.comment)
                            firstline = False

                elif state == 'struct':
                    '''
                    Compound type (struct) declaration.
                    '''

                    result += '\ntype'

                    def procstruct(lines, offset, pointertypes = False):
                        result = ''
                        typename = lines[-1].strip('}; ') or lines[0].split(' ')[2]
                        if pointertypes:
                            result += '\n{}P{name} = ^{name};'.format(' '*offset, name = typename)
                            result += '\n{}PP{name} = ^P{name};'.format(' '*offset, name = typename)
                            result += '\n{}{} = record'.format(' '*offset, typename)
                        else:
                            result += '\n{}{}: record'.format(' '*offset, typename)
                        item = ''
                        nested = []
                        for line in lines[1:len(lines) - 1]:
                            if stripcomment(line).strip() in ('', '{'):
                                continue
                            item += line.strip()
                            if stripcomment(item).strip()[-1] not in ('{', ';'):
                                continue
                            mm = re.search('\(\*(.*)\*\)$', item.strip())
                            comment = ' '.join(['(*', mm.group(1).strip(), '*)'] if mm else '')
                            if item.startswith('struct') or item.startswith('union'):
                                nested += [item]
                            elif nested:
                                nested += [item]
                                if item.startswith('}'):
                                    if nested[0].startswith('union'):
                                        result += '\n  {}case Integer of'.format(' '*offset)
                                        for n, line in zip(count(1), nested[1:len(nested) - 1]):
                                            mm = re.search('\(\*(.*)\*\)$', line.strip())
                                            comment = ' '.join(['(*', mm.group(1).strip(), '*)'] if mm else '')
                                            (cname, ctype) = getnametype(stripcomment(line).rstrip(';'));
                                            (name, typ) = convnametype(cname, ctype)
                                            result += '\n    {}{}: ({}: {});  {}'.format(' '*offset, n, name, typ, comment).rstrip()
                                    else:
                                        result += procstruct(nested, offset + 2)
                                    nested = []
                            else:
                                if item.endswith(');'):
                                    name, args, rettype, varargs = parseprocdecl(item, True)
                                    if typename == 'H5FD_class_t':
                                        args = [arg.replace('PH5FD_t', 'Pointer {PH5FD_t}') for arg in args]
                                        rettype = rettype.replace('PH5FD_t', 'Pointer {PH5FD_t}')
                                    if args:
                                        args = '({})'.format('; '.join(args))
                                    else:
                                        args = ''
                                    if rettype == 'void':
                                        result += '\n  {}{}: procedure{}; cdecl;  {}'.format(' '*offset, name, args, comment).rstrip()
                                    else:
                                        result += '\n  {}{}: function{}: {}; cdecl;  {}'.format(' '*offset, name, args, rettype, comment).rstrip()
                                else:
                                    (cname, ctype) = getnametype(stripcomment(item).rstrip(';'));
                                    (name, typ) = convnametype(cname, ctype)
                                    if typename == 'H5FD_class_t':
                                        typ = typ.replace('array[0..H5FD_MEM_NTYPES - 1]', 'array[H5FD_MEM_DEFAULT..Pred(H5FD_MEM_NTYPES)]')
                                    result += '\n  {}{}: {};  {}'.format(' '*offset, name, typ, comment).rstrip()
                            item = ''

                        result += '\n{}end;'.format(' '*offset)
                        return result

                    result += procstruct(stateinfo, 2, True)

                elif state == 'other':
                    comments = None
                    for i in range(len(stateinfo)):
                        if stateinfo[i].startswith('(*'):
                            comments = stateinfo[i:]
                            stateinfo = stateinfo[:i]
                            break
                    if len(stateinfo) == 1 and re.match('typedef *([^(),]*) +([^(),]*);', stateinfo[0]):
                        '''
                        Type synonym.
                        '''

                        (typ, name) = re.match('typedef *([^(),]*) +([^(),]*);', stateinfo[0]).groups()
                        (name, typ) = convnametype(name.strip(), typ.strip())
                        if name != typ:
                            if prevstate != 'other':
                                result += 'type\n'
                            if name.endswith(']'):
                                result += '  P{} = P{};'.format(re.sub('\[.*', '', name), typ)
                            else:
                                result += '  {} = {};'.format(name, typ)
                                result += '\n  P{name} = ^{name};'.format(name = name)
                    else:
                        '''
                        Procedural type declaration.
                        '''

                        if prevstate != 'other':
                            result += 'type\n'
                        signature = ' '.join(stateinfo)
                        name, args, rettype, varargs = parseprocdecl(re.match('typedef (.*;)', signature.strip()).group(1), True)
                        if rettype == 'void':
                            result += '  {} = procedure({}); cdecl;'.format(name, '; '.join(args))
                        else:
                            result += '  {} = function({}): {}; cdecl;'.format(name, '; '.join(args), rettype)
                        result += '\n  P{name} = ^{name};'.format(name = name)
                    if comments:
                        result += '\n'.join([''] + comments)
                return result

            result = ''
            prevstate = None
            state = None
            stateinfo = []
            for line in lines.split('\n'):
                line = re.sub('^enum', 'typedef enum', line)
                line = re.sub('^struct', 'typedef struct', line)
                if line.startswith('typedef enum'):
                    result += '\n' + process(prevstate, state, stateinfo)
                    prevstate = state
                    state = 'enum'
                    stateinfo = []
                elif line.startswith('typedef struct'):
                    result += '\n' + process(prevstate, state, stateinfo)
                    prevstate = state
                    state = 'struct'
                    stateinfo = []
                elif line.startswith('typedef '):
                    result += '\n' + process(prevstate, state, stateinfo)
                    prevstate = state
                    state = 'other'
                    stateinfo = []
                if state:
                    stateinfo.append(line)
                else:
                    print('WARN: {}'.format(line), file = sys.stderr)
            if state:
                result += '\n' + process(prevstate, state, stateinfo)
            return result

        def procexport(lines):
            '''
            Process sequence of exported symbols.
            '''

            global defs, types, fields, props, init, cinit

            signature = None
            for line in lines.split('\n'):
                if line.startswith('(*') or line.startswith(' *'):
                    continue
                line = re.sub('[(/]\*.*?\*[)/]', '', line.strip())
                if line.startswith('H5_DLLVAR'):
                    '''
                    Exported variable.
                    '''

                    (dummy, ctype, cname) = line.split(' ')
                    cname = cname.strip('_g;')
                    (cname, ctype) = convnametype(cname, ctype)
                    fields += '    F{}: {};\n'.format(cname, ctype)
                    cinit += "  F{cname} := P{ctype}(GetDllProc(FHandle, '{cname}_g'))^;\n".format(cname = cname, ctype = ctype)

                else:
                    '''
                    Exported procedure.
                    '''

                    signature = smartjoin(' ', signature, line)
                    if not ')' in line:
                        continue

                    signature = signature.replace(' (', '(')
                    fname, args, rettype, varargs = parseprocdecl(re.match('H5_DLL (.*;)', signature.strip()).group(1), False)
                    if len(args) > 0:
                        fdef = '(' + '; '.join(args) + ')'
                    else:
                        fdef = ''
                    fdef = fdef + ': ' + rettype

                    if varargs:
                        types += '    // T{} = function{}; cdecl; varargs;\n'.format(fname, fdef)
                        fields += '    // F{}: T{};\n'.format(fname, fname)
                        props += '    // property {}: T{} read {};\n'.format(fname, fname, fname)
                        print('ERROR: Ignoring varargs procedure {}.'.format(fname), file = sys.stderr)
                    else:
                        types += '    T{} = function{}; cdecl;\n'.format(fname, fdef)
                        fields += '    F{}: T{};\n'.format(fname, fname)
                        props += '    property {}: T{} read F{};\n'.format(fname, fname, fname)
                        init += "  @F{0} := GetDllProc(FHandle, '{0}');\n".format(fname)
                    signature = None

        global defs, types, fields, props, init, cinit
        if stateinfo:
            stateinfo = stateinfo.strip('\n')
        if state == 'define':
            newdefs = procdefine(stateinfo).lstrip('\n')
            if len(newdefs) > 0:
                if comment:
                    defs += '\n'
                    defs += comment.strip('\n') + '\n'
                defs += 'const\n'
                defs += newdefs
                defs += '\n'
        elif state == 'typedef':
            newdefs = proctypedef(stateinfo).lstrip('\n')
            if len(newdefs) > 0:
                if comment:
                    defs += '\n'
                    defs += comment.strip('\n') + '\n'
                defs += newdefs
                defs += '\n'
        elif state == 'export':
            newdefs = procexport(stateinfo)

    global state, stateinfo, comment
    state = None
    stateinfo = None
    comment = None

    def setstate(newstate):
        global state, stateinfo, comment
        if stateinfo and stateinfo.endswith('\n'):
            if state:
                process(state, stateinfo, comment)
            state = newstate
            stateinfo = None
            comment = None
        elif newstate != state:
            if newstate == 'comment':
                if state:
                    return
            else:
                if state == 'comment':
                    comment = stateinfo
            process(state, stateinfo, comment)
            if state != 'comment':
                comment = None
            state = newstate
            stateinfo = None

    for line in lines + ['']:
        if line.startswith('(*') or line.startswith(' *'):
            setstate('comment')
        elif not state and line.lstrip(' ').startswith('(*'):
            setstate('comment')
        elif line.startswith('#define'):
            setstate('define')
        elif line.startswith('typedef') or \
             line.startswith('struct') or \
             line.startswith('enum'):
            setstate('typedef')
        elif line.startswith('H5_DLL'):
            setstate('export')
        elif line and not state:
            raise Exception(header, line)
        if state:
            stateinfo = smartjoin('\n', stateinfo, line)
    setstate(None)

    print(file = sys.stderr)

graph = nx.DiGraph()
graph.onodes = []
parsedeps('hdf5.h', graph)
paths = nx.all_pairs_shortest_path_length(graph)
for header in sorted(graph.onodes, key = lambda header: len(paths[header])):
    parse(header)

for line in template.format(date = datetime.date.today(),
                            defs = defs.strip('\n'),
                            classname = classname,
                            types = types.strip('\n'),
                            fields = fields.strip('\n'),
                            props = props.strip('\n'),
                            init = init.strip('\n'),
                            cinit = cinit.strip('\n')).split('\n'):
    print(line.rstrip())
