import re

# Keycmd format which includes the markup for the cursor.
KEYCMD_FORMAT = "%s<span @cursor_style>%s</span>%s"
MODCMD_FORMAT = "<span> %s </span>"


def escape(str):
    for char in ['\\', '@']:
        str = str.replace(char, '\\'+char)

    return str


def uzbl_escape(str):
    return "@[%s]@" % escape(str) if str else ''


class Keylet(object):
    '''Small per-instance object that tracks all the keys held and characters
    typed.'''

    def __init__(self):
        # Modcmd tracking
        self.held = set()
        self.ignored = set()
        self.modcmd = ''
        self.is_modcmd = False

        # Keycmd tracking
        self.keycmd = ''
        self.cursor = 0

        self.modmaps = {}
        self.ignores = {}
        self.additions = {}


    def get_keycmd(self):
        '''Get the keycmd-part of the keylet.'''

        return self.keycmd


    def get_modcmd(self):
        '''Get the modcmd-part of the keylet.'''

        if not self.is_modcmd:
            return ''

        return ''.join(self.held) + self.modcmd


    def modmap_key(self, key):
        '''Make some obscure names for some keys friendlier.'''

        if key in self.modmaps:
            return self.modmaps[key]

        elif key.endswith('_L') or key.endswith('_R'):
            # Remove left-right discrimination and try again.
            return self.modmap_key(key[:-2])

        else:
            return key


    def find_addition(self, modkey):
        '''Key has just been pressed, check if this key + the held list
        results in a modkey addition. Return that addition and remove all
        modkeys that created it.'''

        # Intersection of (held list + modkey) and additions.
        added = (self.held | set([modkey])) & set(self.additions.keys())
        for key in added:
            if key == modkey or modkey in self.additions[key]:
                self.held -= self.additions[key]
                return key

        # Held list + ignored list + modkey.
        modkeys = self.held | self.ignored | set([modkey])
        for (key, value) in self.additions.items():
            if modkeys.issuperset(value):
                self.held -= value
                return key

        return modkey


    def key_ignored(self, key):
        '''Check if the given key is ignored by any ignore rules.'''

        for (glob, match) in self.ignores.items():
            if match(key):
                return True

        return False


    def __repr__(self):
        '''Return a string representation of the keylet.'''

        l = []
        if self.is_modcmd:
            l.append('modcmd=%r' % self.get_modcmd())

        elif self.held:
            l.append('held=%r' % ''.join(sorted(self.held)))

        if self.keycmd:
            l.append('keycmd=%r' % self.get_keycmd())

        return '<keylet(%s)>' % ', '.join(l)


def add_modmap(uzbl, key, map):
    '''Add modmaps.

    Examples:
        set modmap = request MODMAP
        @modmap <Control> <Ctrl>
        @modmap <ISO_Left_Tab> <Shift-Tab>
        ...

    Then:
        @bind <Shift-Tab> = <command1>
        @bind <Ctrl>x = <command2>
        ...

    '''

    assert len(key)
    modmaps = uzbl.keylet.modmaps

    if key[0] == "<" and key[-1] == ">":
        key = key[1:-1]

    modmaps[key] = map
    uzbl.event("NEW_MODMAP", key, map)


def modmap_parse(uzbl, map):
    '''Parse a modmap definiton.'''

    split = [s.strip() for s in map.split(' ') if s.split()]

    if not split or len(split) > 2:
        raise Exception('Invalid modmap arugments: %r' % map)

    add_modmap(uzbl, *split)


def add_key_ignore(uzbl, glob):
    '''Add an ignore definition.

    Examples:
        set ignore_key = request IGNORE_KEY
        @ignore_key <Shift>
        @ignore_key <ISO_*>
        ...
    '''

    assert len(glob) > 1
    ignores = uzbl.keylet.ignores

    glob = "<%s>" % glob.strip("<> ")
    restr = glob.replace('*', '[^\s]*')
    match = re.compile(restr).match

    ignores[glob] = match
    uzbl.event('NEW_KEY_IGNORE', glob)


def add_modkey_addition(uzbl, modkeys, result):
    '''Add a modkey addition definition.

    Examples:
        set mod_addition = request MODKEY_ADDITION
        @mod_addition <Shift> <Control> <Meta>
        @mod_addition <Left> <Up> <Left-Up>
        @mod_addition <Right> <Up> <Right-Up>
        ...

    Then:
        @bind <Right-Up> = <command1>
        @bind <Meta>o = <command2>
        ...
    '''

    additions = uzbl.keylet.additions
    modkeys = set(modkeys)

    assert len(modkeys) and result and result not in modkeys

    for (existing_result, existing_modkeys) in additions.items():
        if existing_result != result:
            assert modkeys != existing_modkeys

    additions[result] = modkeys
    uzbl.event('NEW_MODKEY_ADDITION', modkeys, result)


def modkey_addition_parse(uzbl, modkeys):
    '''Parse modkey addition definition.'''

    keys = filter(None, map(unicode.strip, modkeys.split(" ")))
    keys = ['<%s>' % key.strip("<>") for key in keys if key.strip("<>")]

    assert len(keys) > 1
    add_modkey_addition(uzbl, keys[:-1], keys[-1])


def clear_keycmd(uzbl, *args):
    '''Clear the keycmd for this uzbl instance.'''

    k = uzbl.keylet
    k.keycmd = ''
    k.cursor = 0
    del uzbl.config['keycmd']
    uzbl.event('KEYCMD_CLEARED')


def clear_modcmd(uzbl, clear_held=False):
    '''Clear the modcmd for this uzbl instance.'''

    k = uzbl.keylet
    k.modcmd = ''
    k.is_modcmd = False
    if clear_held:
        k.ignored = set()
        k.held = set()

    del uzbl.config['modcmd']
    uzbl.event('MODCMD_CLEARED')


def clear_current(uzbl):
    '''Clear the modcmd if is_modcmd else clear keycmd.'''

    if uzbl.keylet.is_modcmd:
        clear_modcmd(uzbl)

    else:
        clear_keycmd(uzbl)


def focus_changed(uzbl, *args):
    '''Focus to the uzbl instance has now been lost which means all currently
    held keys in the held list will not get a KEY_RELEASE event so clear the
    entire held list.'''

    clear_modcmd(uzbl, clear_held=True)


def update_event(uzbl, k, execute=True):
    '''Raise keycmd & modcmd update events.'''

    keycmd, modcmd = k.get_keycmd(), k.get_modcmd()

    if k.is_modcmd:
        uzbl.event('MODCMD_UPDATE', k)

    else:
        uzbl.event('KEYCMD_UPDATE', k)

    if uzbl.config.get('modcmd_updates', '1') == '1':
        new_modcmd = k.get_modcmd()
        if not new_modcmd:
            del uzbl.config['modcmd']

        elif new_modcmd == modcmd:
            uzbl.config['modcmd'] = MODCMD_FORMAT % uzbl_escape(modcmd)

    if uzbl.config.get('keycmd_events', '1') != '1':
        return

    new_keycmd = k.get_keycmd()
    if not new_keycmd:
        del uzbl.config['keycmd']

    elif new_keycmd == keycmd:
        # Generate the pango markup for the cursor in the keycmd.
        curchar = keycmd[k.cursor] if k.cursor < len(keycmd) else ' '
        chunks = [keycmd[:k.cursor], curchar, keycmd[k.cursor+1:]]
        value = KEYCMD_FORMAT % tuple(map(uzbl_escape, chunks))

        uzbl.config['keycmd'] = value


def inject_str(str, index, inj):
    '''Inject a string into string at at given index.'''

    return "%s%s%s" % (str[:index], inj, str[index:])


def get_keylet_and_key(uzbl, key, add=True):
    '''Return the keylet and apply any transformations to the key as defined
    by the modmapping or modkey addition rules. Return None if the key is
    ignored.'''

    keylet = uzbl.keylet
    key = keylet.modmap_key(key)
    if len(key) == 1:
        return (keylet, key)

    modkey = "<%s>" % key.strip("<>")

    if keylet.key_ignored(modkey):
        if add:
            keylet.ignored.add(modkey)

        elif modkey in keylet.ignored:
            keylet.ignored.remove(modkey)

    modkey = keylet.find_addition(modkey)

    if keylet.key_ignored(modkey):
        return (keylet, None)

    return (keylet, modkey)


def key_press(uzbl, key):
    '''Handle KEY_PRESS events. Things done by this function include:

    1. Ignore all shift key presses (shift can be detected by capital chars)
    3. In non-modcmd mode:
         a. append char to keycmd
    4. If not in modcmd mode and a modkey was pressed set modcmd mode.
    5. If in modcmd mode the pressed key is added to the held keys list.
    6. Keycmd is updated and events raised if anything is changed.'''

    (k, key) = get_keylet_and_key(uzbl, key.strip())
    if not key:
        return

    if key.lower() == '<space>' and not k.held and k.keycmd:
        k.keycmd = inject_str(k.keycmd, k.cursor, ' ')
        k.cursor += 1

    elif not k.held and len(key) == 1:

        if uzbl.config.get('keycmd_events', '1') != '1':
            k.keycmd = ''
            k.cursor = 0
            del uzbl.config['keycmd']
            return

        k.keycmd = inject_str(k.keycmd, k.cursor, key)
        k.cursor += 1

    elif len(key) > 1:
        k.is_modcmd = True
        if key not in k.held:
            k.held.add(key)

    else:
        k.is_modcmd = True
        k.modcmd += key

    update_event(uzbl, k)


def key_release(uzbl, key):
    '''Respond to KEY_RELEASE event. Things done by this function include:

    1. Remove the key from the keylet held list.
    2. If in a mod-command then raise a MODCMD_EXEC.
    3. Check if any modkey is held, if so set modcmd mode.
    4. Update the keycmd uzbl variable if anything changed.'''

    (k, key) = get_keylet_and_key(uzbl, key.strip(), add=False)

    if key in k.held:
        if k.is_modcmd:
            uzbl.event('MODCMD_EXEC', k)

        k.held.remove(key)
        clear_modcmd(uzbl)


def set_keycmd(uzbl, keycmd):
    '''Allow setting of the keycmd externally.'''

    k = uzbl.keylet
    k.keycmd = keycmd
    k.cursor = len(keycmd)
    update_event(uzbl, k, False)


def inject_keycmd(uzbl, keycmd):
    '''Allow injecting of a string into the keycmd at the cursor position.'''

    k = uzbl.keylet
    k.keycmd = inject_str(k.keycmd, k.cursor, keycmd)
    k.cursor += len(keycmd)
    update_event(uzbl, k, False)


def append_keycmd(uzbl, keycmd):
    '''Allow appening of a string to the keycmd.'''

    k = uzbl.keylet
    k.keycmd += keycmd
    k.cursor = len(k.keycmd)
    update_event(uzbl, k, False)


def keycmd_strip_word(uzbl, sep):
    ''' Removes the last word from the keycmd, similar to readline ^W '''

    sep = sep or ' '
    k = uzbl.keylet
    if not k.keycmd:
        return

    head, tail = k.keycmd[:k.cursor].rstrip(sep), k.keycmd[k.cursor:]
    rfind = head.rfind(sep)
    head = head[:rfind] if rfind + 1 else ''
    k.keycmd = head + tail
    k.cursor = len(head)
    update_event(uzbl, k, False)


def keycmd_backspace(uzbl, *args):
    '''Removes the character at the cursor position in the keycmd.'''

    k = uzbl.keylet
    if not k.keycmd or not k.cursor:
        return

    k.keycmd = k.keycmd[:k.cursor-1] + k.keycmd[k.cursor:]
    k.cursor -= 1
    update_event(uzbl, k, False)


def keycmd_delete(uzbl, *args):
    '''Removes the character after the cursor position in the keycmd.'''

    k = uzbl.keylet
    if not k.keycmd:
        return

    k.keycmd = k.keycmd[:k.cursor] + k.keycmd[k.cursor+1:]
    update_event(uzbl, k, False)


def keycmd_exec_current(uzbl, *args):
    '''Raise a KEYCMD_EXEC with the current keylet and then clear the
    keycmd.'''

    uzbl.event('KEYCMD_EXEC', uzbl.keylet)
    clear_keycmd(uzbl)


def set_cursor_pos(uzbl, index):
    '''Allow setting of the cursor position externally. Supports negative
    indexing and relative stepping with '+' and '-'.'''

    k = uzbl.keylet
    if index == '-':
        cursor = k.cursor - 1

    elif index == '+':
        cursor = k.cursor + 1

    else:
        cursor = int(index.strip())
        if cursor < 0:
            cursor = len(k.keycmd) + cursor + 1

    if cursor < 0:
        cursor = 0

    if cursor > len(k.keycmd):
        cursor = len(k.keycmd)

    k.cursor = cursor
    update_event(uzbl, k, False)


# plugin init hook
def init(uzbl):
    '''Export functions and connect handlers to events.'''

    connect_dict(uzbl, {
        'APPEND_KEYCMD':        append_keycmd,
        'FOCUS_GAINED':         focus_changed,
        'FOCUS_LOST':           focus_changed,
        'IGNORE_KEY':           add_key_ignore,
        'INJECT_KEYCMD':        inject_keycmd,
        'KEYCMD_BACKSPACE':     keycmd_backspace,
        'KEYCMD_DELETE':        keycmd_delete,
        'KEYCMD_EXEC_CURRENT':  keycmd_exec_current,
        'KEYCMD_STRIP_WORD':    keycmd_strip_word,
        'KEYCMD_CLEAR':         clear_keycmd,
        'KEY_PRESS':            key_press,
        'KEY_RELEASE':          key_release,
        'MODKEY_ADDITION':      modkey_addition_parse,
        'MODMAP':               modmap_parse,
        'SET_CURSOR_POS':       set_cursor_pos,
        'SET_KEYCMD':           set_keycmd,
    })

    export_dict(uzbl, {
        'add_key_ignore':       add_key_ignore,
        'add_modkey_addition':  add_modkey_addition,
        'add_modmap':           add_modmap,
        'append_keycmd':        append_keycmd,
        'clear_current':        clear_current,
        'clear_keycmd':         clear_keycmd,
        'clear_modcmd':         clear_modcmd,
        'inject_keycmd':        inject_keycmd,
        'keylet':               Keylet(),
        'set_cursor_pos':       set_cursor_pos,
        'set_keycmd':           set_keycmd,
    })

# vi: set et ts=4:
