import sys

# --- Operator definitions ---
OPERATORS = {
    '||': (1, lambda a, b: int(bool(a) or bool(b))),
    '&&': (2, lambda a, b: int(bool(a) and bool(b))),
    '==': (3, lambda a, b: int(a == b)),
    '!=': (3, lambda a, b: int(a != b)),
    '<':  (4, lambda a, b: int(a < b)),
    '<=': (4, lambda a, b: int(a <= b)),
    '>':  (4, lambda a, b: int(a > b)),
    '>=': (4, lambda a, b: int(a >= b)),
    '+':  (5, lambda a, b: a + b),
    '-':  (5, lambda a, b: a - b),
    '*':  (6, lambda a, b: a * b),
    '/':  (6, lambda a, b: a // b if b != 0 else 0),
    '%':  (6, lambda a, b: a % b),
}

# --- Tokenizer, Parser, Evaluator (including indexing) ---
def tokenize(expr):
    token_spec = [
        ('NUMBER', r'\d+'),
        ('ID',     r'[A-Za-z_]\w*'),
        ('INDEX',  r'\['),
        ('OP',     r'\|\||&&|==|!=|<=|>=|[+\-*/%<>=\(\)]|\]'),
        ('SKIP',   r'[ \t]+'),
    ]
    tok_regex = '|'.join(f'(?P<{n}>{p})' for n,p in token_spec)
    tokens = []
    pos = 0
    while pos < len(expr):
        mo = re.match(tok_regex, expr[pos:])
        if not mo:
            raise SyntaxError(f"Bad token at '{expr[pos:]}'")
        kind, val = mo.lastgroup, mo.group()
        pos += len(val)
        if kind == 'NUMBER':
            tokens.append(('NUMBER', int(val)))
        elif kind in ('ID','INDEX','OP'):
            tokens.append((kind, val))
        # SKIP: ignore
    return tokens

def shunting_yard(tokens):
    out, stack = [], []
    i = 0
    while i < len(tokens):
        typ, val = tokens[i]
        if typ in ('NUMBER','ID'):
            # handle indexing
            out.append((typ,val))
            if i+1 < len(tokens) and tokens[i+1][0]=='INDEX':
                # parse [ ... ]
                i+=2
                sub = []
                depth=1
                while i<len(tokens) and depth>0:
                    if tokens[i][0]=='INDEX': depth+=1
                    if tokens[i][1]==']': depth-=1
                    if depth>0: sub.append(tokens[i])
                    i+=1
                sub_rpn = shunting_yard(sub)
                out+=sub_rpn
                out.append(('OP','index'))
                continue
        elif typ=='OP':
            if val=='(':
                stack.append(val)
            elif val==')':
                while stack and stack[-1]!='(':
                    out.append(('OP',stack.pop()))
                stack.pop()
            else:
                while stack and stack[-1]!='(' and OPERATORS[stack[-1]][0]>=OPERATORS[val][0]:
                    out.append(('OP',stack.pop()))
                stack.append(val)
        i+=1
    while stack:
        out.append(('OP',stack.pop()))
    return out

def eval_rpn(rpn, env):
    stk=[]
    for typ,val in rpn:
        if typ=='NUMBER':
            stk.append(val)
        elif typ=='ID':
            if val in env.variables: stk.append(env.variables[val])
            else: raise RuntimeError(f"Unknown var '{val}'")
        elif typ=='OP':
            if val=='index':
                idx=stk.pop(); arr=stk.pop()
                if not isinstance(arr,(list,tuple)): raise RuntimeError("Not an array")
                stk.append(arr[idx])
            elif val=='-' and len(stk)==1:
                a=stk.pop(); stk.append(-a)
            else:
                b=stk.pop(); a=stk.pop()
                stk.append(OPERATORS[val][1](a,b))
    if len(stk)!=1: raise RuntimeError("Bad expr")
    return stk[0]

def eval_expr(expr, env):
    return eval_rpn(shunting_yard(tokenize(expr)), env)

# --- Environment & Return exception ---
class ReturnValue(Exception):
    def __init__(self,value): self.value=value

class Environment:
    def __init__(self, parent=None, argv=None):
        self.variables = {}
        self.functions = {}
        self.structs   = {}
        self.externs = {
            'putchar': lambda x: print(chr(x),end=''),
            'putstr':  lambda s: print(s,end=''),
            'putint':  lambda i: print(i,end=''),
            'getchar': lambda: ord(input()[0]) if input() else 0,
            'puts':    lambda s: print(s),
            'getint':  lambda: int(input()),
            'abs':     abs,
            'max':     max,
            'min':     min,
        }
        self.parent = parent
        # Setup argv as a list of strings
        self.variables['argv'] = argv or []

# --- Comment stripper, block extractor, struct & function parsers ---
def strip_comments(lines):
    out=[]; ml=False
    for l in lines:
        s=l.strip()
        if ml:
            if '*/' in s: ml=False; s=s.split('*/',1)[1]
            else: continue
        if '/*' in s: ml=True; s=s.split('/*',1)[0]
        if '//' in s: s=s.split('//',1)[0]
        if s.strip(): out.append(s)
    return out

def extract_block(lines,start):
    blk=[]; depth=0
    for i in range(start,len(lines)):
        l=lines[i]
        if '{' in l: depth+=1
        if '}' in l: depth-=1
        blk.append(l)
        if depth==0: return blk,i+1
    raise RuntimeError("Unclosed block")

def parse_struct(lines,env,i):
    m=re.match(r'struct\s+(\w+)\s*{',lines[i])
    if not m: raise RuntimeError("Bad struct")
    name=m.group(1); body,next_i=extract_block(lines,i)
    fields=[]
    for fld in body[1:-1]:
        if fld.startswith('auto '):
            parts=[f.strip() for f in fld[len('auto '):-1].split(',')]
            fields+=parts
    env.structs[name]=fields
    return next_i

def parse_functions(lines,env):
    i=0
    while i<len(lines):
        m=re.match(r'(\w+)\s*\(([^)]*)\)\s*{',lines[i])
        if m:
            name=m.group(1)
            params=[p.strip() for p in m.group(2).split(',')] if m.group(2).strip() else []
            body,next_i=extract_block(lines,i)
            env.functions[name]={'params':params,'body':body[1:-1]}
            i=next_i
        else:
            i+=1

def parse_expr_args(s):
    args=[]; cur=''; d=0
    for c in s:
        if c==',' and d==0:
            args.append(cur.strip()); cur=''
        else:
            if c=='(': d+=1
            if c==')': d-=1
            cur+=c
    if cur.strip(): args.append(cur.strip())
    return args

# --- Core executor ---
def exec_block(lines, env, base_lineno=1):
    i=0
    while i<len(lines):
        l=lines[i]
        try:
            # return
            m=re.match(r'return(?:\s+(.*))?;?$',l)
            if m:
                val=eval_expr(m.group(1),env) if m.group(1) else 0
                raise ReturnValue(val)

            # extrn
            if l.startswith('extrn '):
                for name in l[len('extrn '):-1].split(','):
                    if name.strip() not in env.externs:
                        raise RuntimeError(f"Unknown extern '{name}'")
                i+=1; continue

            # auto
            if l.startswith('auto '):
                for v in l[len('auto '):-1].split(','):
                    env.variables[v.strip()]=0
                i+=1; continue

            # if / else if / else
            if l.startswith('if '):
                cond=re.match(r'if\s*\((.*)\)\s*{',l).group(1)
                blk,nx=extract_block(lines,i)
                if eval_expr(cond,env):
                    exec_block(blk[1:-1],Environment(env,env.variables.get('argv',[])), base_lineno+i+1)
                    i=nx
                    # skip any trailing else/else if
                    while i<len(lines) and lines[i].startswith(('else if','else')):
                        _,i=extract_block(lines,i)
                    continue
                else:
                    i=nx
                    # handle else if / else chain
                    while i<len(lines):
                        if lines[i].startswith('else if'):
                            cond=re.match(r'else if\s*\((.*)\)\s*{',lines[i]).group(1)
                            blk2,nx2=extract_block(lines,i)
                            if eval_expr(cond,env):
                                exec_block(blk2[1:-1],Environment(env,env.variables.get('argv',[])),base_lineno+i+1)
                                i=nx2
                                # skip rest
                                while i<len(lines) and lines[i].startswith(('else if','else')):
                                    _,i=extract_block(lines,i)
                                break
                            i=nx2
                        elif lines[i].startswith('else'):
                            blk2,nx2=extract_block(lines,i)
                            exec_block(blk2[1:-1],Environment(env,env.variables.get('argv',[])),base_lineno+i+1)
                            i=nx2; break
                        else:
                            break
                    continue

            # for loop
            if l.startswith('for '):
                m=re.match(r'for\s*\(([^;]*);([^;]*);([^\)]*)\)\s*{',l)
                init,cond,post=m.group(1).strip(),m.group(2).strip(),m.group(3).strip()
                blk,nx=extract_block(lines,i)
                if init: exec_block([init+';'],env,base_lineno+i)
                while eval_expr(cond,env):
                    exec_block(blk[1:-1],Environment(env,env.variables.get('argv',[])),base_lineno+i+1)
                    if post: exec_block([post+';'],env,base_lineno+i)
                i=nx; continue

            # while loop
            if l.startswith('while '):
                cond=re.match(r'while\s*\((.*)\)\s*{',l).group(1)
                blk,nx=extract_block(lines,i)
                while eval_expr(cond,env):
                    exec_block(blk[1:-1],Environment(env,env.variables.get('argv',[])),base_lineno+i+1)
                i=nx; continue

            # assignment (with function-call RHS support)
            m=re.match(r'(\w+)(\.\w+)?\s*=\s*(.+);?$',l)
            if m:
                var,field,expr=m.group(1),m.group(2),m.group(3)
                # check function call on RHS
                m2=re.match(r'(\w+)\((.*)\)$',expr)
                if m2 and m2.group(1) in env.functions:
                    fn,margs=m2.group(1),m2.group(2)
                    vals=[eval_expr(a,env) for a in parse_expr_args(margs)]
                    func=env.functions[fn]
                    new_env=Environment(env,env.variables.get('argv',[]))
                    for p,v in zip(func['params'],vals): new_env.variables[p]=v
                    try:
                        val=exec_block(func['body'],new_env,base_lineno+i+1)
                    except ReturnValue as r: val=r.value
                else:
                    val=eval_expr(expr,env)
                if field:
                    f=field[1:]
                    if isinstance(env.variables.get(var),dict):
                        env.variables[var][f]=val
                    else:
                        raise RuntimeError(f"Not struct instance")
                else:
                    env.variables[var]=val
                i+=1; continue

            # function or extern call
            m=re.match(r'(\w+)\((.*)\);?$',l)
            if m:
                fn,args=m.group(1),m.group(2)
                if fn in env.externs:
                    vals=[eval_expr(a,env) for a in parse_expr_args(args)]
                    env.externs[fn](*vals)
                elif fn in env.functions:
                    vals=[eval_expr(a,env) for a in parse_expr_args(args)]
                    func=env.functions[fn]
                    new_env=Environment(env,env.variables.get('argv',[]))
                    for p,v in zip(func['params'],vals): new_env.variables[p]=v
                    try:
                        exec_block(func['body'],new_env,base_lineno+i+1)
                    except ReturnValue: pass
                else:
                    raise RuntimeError(f"Unknown function '{fn}'")
                i+=1; continue

        except ReturnValue as ret:
            return ret.value

        except RuntimeError as e:
            raise RuntimeError(f"Error at line {base_lineno+i}: {l}\n  {e}")

        i+=1
    return 0

# ... debug_block(), repl() remain unchanged, but pass argv through Environment exactly like above ...

def main():
    if len(sys.argv)>1:
        filename=sys.argv[1]
        argv_vars=sys.argv[1:]  # include script name and args
        code=open(filename).read().splitlines()
        lines=strip_comments(code)
        env=Environment(argv=argv_vars)
        i=0
        while i<len(lines):
            if lines[i].startswith('struct'):
                i=parse_struct(lines,env,i)
            else:
                i+=1
        parse_functions(lines,env)
        try:
            exec_block(lines,env)
        except RuntimeError as e:
            print(f"Runtime error: {e}")
    else:
        repl()

if __name__=="__main__":
    main()