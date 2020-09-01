#!/usr/bin/env python3
# cdecl.py

import sys
import signal
from enum import Enum

try:
    import readline
    READLINE = True
except ModuleNotFoundError:
    READLINE = False

PROMPT = "cdecl: "
INDENT = "    "

############################################
# LEXER
############################################

# I don't consider parens to be punctuation since I process them straight off
# the bat by using them to organize the other tokens into groups
PUNCTUATION = ['[', ']', ',', '*']

PRIMTYPES = ['bool', 'int', 'short', 'long', 'char', 'void', 'float', 'double',
        'long double', 'long long', 'long int']

# Types which we can append long to
# Currently don't handle `long long int` but I just can't be bothered
LONGTYPES = ['double', 'long', 'int']

MODIFIERS = ['unsigned', 'signed', 'const', 'struct']

KEYWORDS = PRIMTYPES + MODIFIERS

class LexerError(Exception):
    def __init__(self, msg):
        super().__init__(msg)

class Token(object):
    def __init__(self, start, string=None):
        """If string=None, then create a token group instead."""
        self.start = start
        self.string = string
        self.modifiers = []

        if string == None:
            self.length = None # don't know yet. set it later
            self.items = []
        else:
            self.length = len(string)
            self.items = None

    def is_type(self):
        """Is this a type name?"""
        return self.is_name() and (self.string in PRIMTYPES \
                or 'struct' in self.modifiers)

    def add_modifier(self, modStr):
        """Add the flag corresponding to the modifier."""
        if modStr in self.modifiers or modStr not in MODIFIERS:
            raise RuntimeError('internal error')
        self.modifiers.append(modStr)

    def has_modifier(self, modStr):
        """Does this type have the following modifier?"""
        return modStr in self.modifiers

    def is_group(self):
        """Is this a token group?"""
        return self.string == None

    def is_name(self):
        """Is this a type or variable name?"""
        return self.string != None and (self.string[0] == '_' \
                or self.string[0].isalpha())

    def is_num(self):
        """Is this token an integer?"""
        return self.string != None and self.string[0].isdigit()

    def get_num(self):
        """Return the integer that this token represents."""
        if self.is_group() or not self.is_num():
            raise RuntimeError('internal error')
        return int(self.string)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]

    def append(self, tok):
        self.items.append(tok)

    def display(self, indent=0): # Used for debugging
        """Recursively print out all the lexed tokens and groups."""
        if self.is_group():
            print(INDENT * indent + 'group: {')
            for tok in self.items:
                tok.display(indent + 1)
            print(INDENT * indent + '}')
        elif self.is_num():
            print(INDENT * indent + 'num: ' + self.string)
        else:
            print(INDENT * indent + 'tok: ' + self.string)

    def underline(self):
        """Underline this token with carats on the next line."""
        print(' ' * (self.start + len(PROMPT)), end='')
        print('^' * self.length)

class Lexer(object):
    def __init__(self, declString):
        """declString is the string to be lexed."""
        self.string = declString
        self.curIndex = 0 

    def underline(self):
        """Print a carat on the next line pointing to current index"""
        print(' ' * (self.curIndex + len(PROMPT)), end='')
        print('^')

    def nextchar(self):
        """Returns next character in string. Moves forward by one."""
        self.curIndex += 1
        if self.curIndex >= len(self.string):
            return None
        return self.string[self.curIndex]

    def peekchar(self):
        """Return next character. Doesn't move forward or backward."""
        if self.curIndex + 1 >= len(self.string):
            return None
        return self.string[self.curIndex + 1]

    def curchar(self):
        """Return current character."""
        if self.curIndex >= len(self.string):
            return None
        return self.string[self.curIndex]

    def parse_tokens(self, nested=True):
        """Parse a token group. Will expect closing paren if nested=True."""
        group = Token(self.curIndex - 1 if nested else self.curIndex)
        while True:
            if nested and self.curchar() == ')':
                self.nextchar()
                group.length = self.curIndex - group.start
                return group

            tok = self.next_token()
            if tok == None:
                if nested:
                    raise LexerError('expected closing )')
                group.length = self.curIndex - group.start
                return group

            group.append(tok)

    def skip_space(self):
        ch = self.curchar()
        while ch != None and ch.isspace():
            ch = self.nextchar()
        return ch

    def parse_ident(self):
        ch = self.skip_space()
        if ch != None and (ch == '_' or ch.isalpha()):
            nameStart = self.curIndex
            ch = self.nextchar()
            # Continue until invalid ident character
            while ch != None and (ch == '_' or ch.isalpha() or ch.isdigit()):
                ch = self.nextchar()
            # Extract the name
            tokStr = self.string[nameStart:self.curIndex]
            return Token(nameStart, tokStr)
        return None

    def parse_type(self, tok):
        """Pretty long and dank function due to the many possibilities when
        stringing together groups of modifiers and type keywords."""
        if tok.string == 'struct':
            name = self.parse_ident() # Get the name of the struct
            if name == None:
                self.underline()
                raise LexerError('expected an identifier')
            if name.string in KEYWORDS:
                name.underline()
                raise LexerError('cannot use \'' + name.string \
                        + '\' as an identifier')
            tok.length = self.curIndex - tok.start
            tok.add_modifier('struct')
            tok.string = name.string
            return tok
        elif tok.string in PRIMTYPES:
            # Check for 'long-able' types which we can prefix with long
            if tok.string == 'long':
                initialIndex = self.curIndex # We may need to rewind
                nextTok = self.parse_ident()
                if nextTok != None and nextTok.string in LONGTYPES:
                    tok.string += ' ' + nextTok.string
                    tok.length = self.curIndex - tok.start
                    return tok
                # Okay, wasn't what we thought. Rewind and just return long
                self.curIndex = initialIndex
            return tok
        elif tok.string in MODIFIERS:
            mods = [tok.string] # build up list of modifiers
            beforeNextTok = self.curIndex # In case we need to rewind
            nextTok = self.parse_ident()
            while nextTok != None and nextTok.string in MODIFIERS:
                # We can't repeat the same modifier twice
                if nextTok in mods:
                    nextTok.underline()
                    raise LexerError('cannot use modifiers twice')
                # If it's the struct keyword then the only valid preceding
                # modifier is the 'const' keyword (and no other modifiers
                # are allowed
                if nextTok.string == 'struct':
                    if len(mods) != 1 or mods[0] != 'const':
                        tok.length = self.curIndex - tok.start
                        tok.underline()
                        raise LexerError('the only valid modifier for ' + \
                                'struct is \'const\'')
                    # Now re-parse as a struct (but add const modifier)
                    tok.length = self.curIndex - tok.start
                    tok.add_modifier('const')
                    tok.string = 'struct'
                    return self.parse_type(tok)
                # Make sure we don't have signed AND unsigned.
                if nextTok.string in ['signed', 'unsigned']:
                    # We've already ensured that the modifiers are unique, so
                    # it's safe to check it like this
                    if 'signed' in mods or 'unsigned' in mods:
                        tok.length = self.curIndex - tok.start
                        tok.underline()
                        raise LexerError('cannot have signed and unsigned')

                mods.append(nextTok.string)
                beforeNextTok = self.curIndex # we might need to rewind later
                nextTok = self.parse_ident()

            if nextTok == None or nextTok.string not in PRIMTYPES:
                # If the last modifier was 'signed' or 'unsigned', then you 
                # aren't required to list a primitive type after it, since it 
                # defaults to 'int'
                if mods[-1] in ['signed', 'unsigned']: 
                    # Rewind to exclude nextTok
                    self.curIndex = beforeNextTok
                    # Set the type to 'int'
                    tok.string = 'int'
                elif nextTok == None:
                    self.underline()
                    raise LexerError('expected a type name or modifier')
                else:
                    nextTok.underline()
                    raise LexerError('expected a type name or modifier')
            else:
                # Set the type name to the primitive type name
                tok.string = nextTok.string

            tok.length = self.curIndex - tok.start
            for mod in mods:
                tok.add_modifier(mod)
            # Re-parse as a primitive type (with modifiers added)
            return self.parse_type(tok)

    def next_token(self):
        """Return next token (could be a token group)."""
        ch = self.skip_space()
        if ch == None:
            return None

        if ch in PUNCTUATION:
            if ch == '*':
                initialPos = self.curIndex # We may need to rewind to here
                self.nextchar()
                ident = self.parse_ident()
                if ident != None and ident.string == 'const':
                    tok = Token(initialPos, ch)
                    tok.add_modifier('const')
                    tok.length = self.curIndex - initialPos
                    return tok
                # Okay, wasn't a constant pointer - rewind
                self.curIndex = initialPos
            # Parse as regular punctuation
            self.nextchar()
            return Token(self.curIndex - 1, ch)

        # If not punctuation, maybe start of an identifier or type name?
        tok = self.parse_ident()
        if tok != None:
            if tok.string in KEYWORDS:
                return self.parse_type(tok)
            return tok

        # Maybe it's the start of a number?
        if ch.isdigit():
            numStart = self.curIndex
            ch = self.nextchar()
            # Continue until non-digit
            while ch != None and ch.isdigit():
                ch = self.nextchar()
            # Extract the name
            tokStr = self.string[numStart:self.curIndex]
            return Token(numStart, tokStr)

        # Maybe it's a bunch of tokens enclosed in '(' and ')'?
        if ch == '(':
            self.nextchar()
            group = self.parse_tokens()
            return group

        print('^'.rjust(self.curIndex + 1 + len(PROMPT)))
        if ch == ')':
            raise LexerError('unmatched )')
        else:
            raise LexerError('invalid character')

############################################
# PARSER
############################################

class ParserError(Exception):
    def __init__(self, msg):
        super().__init__(msg)
class Node(object):
    def __init__(self, child):
        self.child = child
        self.warnings = []

    def add_warning(self, msg):
        self.warnings.append(msg)

    def display(self, indent=0):
        for warn in self.warnings:
            print(INDENT * indent + '\033[33;1mWarning:\033[0;0m ' + warn)

    def colour_name(self, name):
        if len(self.warnings) > 0:
            return '\033[33;1m' + name + '\033[0;0m'
        else:
            return '\033[1m' + name + '\033[0m'

class Array(Node):
    def __init__(self, child, size):
        super().__init__(child)
        self.size = size

    def display(self, indent=0):
        size = str(self.size) if self.size != None else '??'
        print(INDENT * indent + self.colour_name('array') + ' of size ' \
                + size + ' containing')
        super().display(indent)
        self.child.display(indent + 1)

class Pointer(Node):
    def __init__(self, child, isConst=False):
        super().__init__(child)
        self.is_const = isConst

    def display(self, indent=0):
        print(INDENT * indent, end='')
        if self.is_const:
            print('constant ', end='')
        print(self.colour_name('pointer') + ' to ', end='')
        if self.child == None:
            print('void')
            super().display(indent)
        else:
            print('')
            super().display(indent)
            self.child.display(indent + 1)

class Type(Node):
    def __init__(self, typeTok):
        super().__init__(None) # Named types can't have children
        self.type_name = typeTok.string 
        self.modifiers = typeTok.modifiers

    def display(self, indent=0):
        print(INDENT * indent, end='')

        if 'const' in self.modifiers:
            print('constant ', end='')

        for mod in self.modifiers:
            # Don't bother printing signed, since it's default anyway. Also
            # don't print 'const' since we've already handled that.
            if mod != 'signed' and mod != 'const':
                print(mod, end=' ')

        print(self.colour_name(self.type_name))

class Function(Node):
    """The function return type is the child of this node"""
    def __init__(self, returnType, params):
        super().__init__(returnType) # child = returnType
        self.params = params

    def display(self, indent=0):
        print(INDENT * indent + self.colour_name('function') \
                + ' that returns ', end='')

        if self.child == None:
            print('nothing')
            super().display(indent)
        else:
            print('')
            super().display(indent)
            self.child.display(indent + 1)

        if self.params == None:
            print(INDENT * indent + 'and takes any number of parameters')
        elif len(self.params) == 0:
            print(INDENT * indent + 'and takes no parameters')
        else:
            print(INDENT * indent + 'and takes the parameters')
            for param in self.params:
                param.display(indent + 1)

class Parser(object):
    def __init__(self, tokens, child=None):
        self.tokens = tokens
        if not tokens.is_group() or len(tokens) == 0:
            self.tokens.underline()
            raise ParserError('expected more tokens here')
        self.child = child
        self.index = 0

    def error_at(self, tok, msg):
        print(' ' * (tok.start + len(PROMPT)), end='')
        print('^' * tok.length)
        raise ParserError(msg)
        ch = self.curchar()
        while ch != None and ch.isspace():
            ch = self.nextchar()

    def error(self, msg):
        i = self.index
        if i >= len(self.tokens):
            lastToken = self.tokens[-1]
            spaces = lastToken.start + lastToken.length
            print(' ' * (spaces + len(PROMPT)), end='')
            print('^')
            raise ParserError(msg)
        else:
            self.error_at(self.tokens[i], msg)

    def current(self):
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def peek(self):
        if self.index + 1 >= len(self.tokens):
            return None
        return self.tokens[self.index + 1]

    def next(self):
        self.index += 1
        return self.current()

    def expect(self):
        tok = self.current()
        if tok == None:
            self.error('expected another token')
        return tok

    def check_void_decl(self, voidTok):
        if self.child == None:
            self.error_at(voidTok, 'void on its own is not a valid type')

    def parse(self):
        voidTok = None # might need for later error reporting
        if self.child == None:
            # Parse type name
            if not self.expect().is_type():
                self.error('expected a type name')
            if self.current().string == 'void':
                voidTok = self.current() # Store for error reporting
            else:
                self.child = Type(self.current()) 
            if self.next() == None:
                self.check_void_decl(voidTok)
                return self.child

        # Parse pointers - as much as needed
        while self.current() != None and self.current().string == '*':
            isConst = self.current().has_modifier('const')
            self.child = Pointer(self.child, isConst)
            self.next()

        # NOW WE CAN PARSE SOME OPTIONAL GROUP OR NAME HERE
        parentGroup = None
        if self.current() != None:
            if self.current().is_name():
                if self.current().string in KEYWORDS:
                    self.error('cannot use \'' + self.current().string \
                            + '\' as an identifier')
                self.next()
            elif self.current().is_group():
                parentGroup = self.current()
                self.next()

        # Function parameter list?
        isFunction = False
        params = []
        if self.current() != None and self.current().is_group():
            paramGroup = self.current()
            isFunction = True
            if len(paramGroup) == 0:
                # Accepts any number of parameters, we params=None to show this
                params = None
            elif len(paramGroup) == 1 and paramGroup[0].string == 'void':
                # Accepts no parameters, leave the list as an empty list
                pass
            else:
                # We have to parse the parameter list. In a loop, we collect
                # all the tokens up to ',' or the end of paramGroup into a
                # group then call the parser on that group.
                i = 0 # Current index in the group
                while i < len(paramGroup):
                    # Don't care about starting position for token group (it's
                    # only used for parsing, so set it to None)
                    param = Token(None) # create token group
                    # Collect all the tokens up until ',' or end of the group
                    while i < len(paramGroup):
                        if paramGroup[i].string == ',':
                            i += 1
                            break
                        param.append(paramGroup[i])
                        i += 1
                    # Don't bother setting the length of the token group, it's
                    # just for parsing purposes - we should never need it.
                    params.append(Parser(param).parse()) # Parse the parameter
                    if type(params[-1]) == Function:
                        params[-1].add_warning('illegal in C: this is a raw ' \
                                + 'function being passed as a parameter')
            # Now move past the parameters group
            self.next()

        # Now parse as many array dimensions as needed
        dimensions = []
        while self.current() != None and self.current().string == '[':
            self.next()
            if self.expect().is_num():
                dimensions.append(self.expect().get_num())
                self.next()
            else:
                dimensions.append(None)
            if self.expect().string != ']':
                self.error('expected ]')
            self.next()

        for dim in reversed(dimensions):
            if self.child == None:
                self.error_at(voidTok, 'arrays cannot store void')
            array = Array(self.child, dim)
            if type(self.child) == Function:
                array.add_warning('illegal in C: arrays cannot store ' \
                        + 'raw functions')
            self.child = array

        if self.current() != None:
            self.error('unexpected tokens')

        # Parent the function onto us if we found one
        if isFunction:
            func = Function(self.child, params)
            if type(self.child) == Function:
                func.add_warning('illegal in C: you cannot return a ' \
                        + 'raw function')
            self.child = func

        # Now parent the group onto us if we found one
        if parentGroup != None:
            # Parse the group and parent it onto us
            self.child = Parser(parentGroup, self.child).parse()

        self.check_void_decl(voidTok)
        return self.child

############################################
# MAIN PROGRAM STUFF
############################################
def sigint_handler(sig, frame):
    print('')
    sys.exit(0) # Override Python's default "KeyboardInterrupt" behaviour

if __name__ == '__main__':
    signal.signal(signal.SIGINT, sigint_handler)

    if len(sys.argv) > 1:
        print('Enter hard to understand C declarations and see what they mean')
        print('Pressing Ctrl+C should exit this on most terminals!')
        print('On Windows, use "Windows Terminal" (from the Microsoft Store)')
        print('    ... the normal command line will mess up the colours')
        sys.exit(0)

    if READLINE:
        readline.set_history_length(1000) # How many old inputs are remembered

    while True:
        try:
            line = input('\033[34;1m' + PROMPT + '\033[0;0m')
            if READLINE:
                readline.add_history(line)
        except EOFError:
            print('End of input')
            sys.exit(0)

        line = line.strip()
        if len(line) == 0:
            continue # Skip empty lines
        
        try:
            tokens = Lexer(line).parse_tokens(nested=False)
        except LexerError as error:
            print("\033[33;1mLexer failed\033[0;0m: " + str(error))
            continue
        
        #tokens.display() # for debugging

        try:
            parser = Parser(tokens)
            tree = parser.parse()
        except ParserError as error:
            print("\033[31;1mParser failed\033[0;0m: " + str(error))
            continue

        tree.display()

