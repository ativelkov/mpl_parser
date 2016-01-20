# Copyright (c) 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import re

import utils

colon_pattern = re.compile('^(?P<dash>\s*-\s+)?'
                           '((?:(?P<key>.*?(?:\\w))\\s*:(?:\\s+(?P<value>.*))?)|'
                           '(?P<s_value>.*))$')

# colon_pattern = re.compile('^(\s*-\s+)?'
#                            '(<KEY>.*(?:\w))\s*:\s*$')


def parse(line):
    m = re.match(colon_pattern, line)
    if m:
        return (m.groupdict().get('key'),
                m.groupdict().get('value') or m.groupdict().get('s_value'),
                m.groupdict().get('dash') is not None)
    else:
        raise MacroParseException()


class Macro(object):
    def __init__(self):
        self.children = None

    def serialize(self):
        pass

    def is_done(self):
        return True

    @property
    def indent(self):
        return 0

    def get_kwords(self):
        return []

class MacroParseException(Exception):
    pass


class SingleValue(Macro):
    def __init__(self, expression):
        super(SingleValue, self).__init__()
        self.expression = expression

    def serialize(self):
        return self.expression

    def __str__(self):
        return self.expression


class KeyPair(Macro):
    def __init__(self, key, value):
        super(KeyPair, self).__init__()
        self.key = key
        self.value = value

        if isinstance(self.value, Macro):
            self.children = [self.value]

    def serialize(self):
        if isinstance(self.value, Macro):
            return {self.key: self.value.serialize()}
        else:
            return {self.key: self.value}

    def __str__(self):
        return "%s: %s" % (self.key, self.value)


class MacroBlock(Macro):
    def __init__(self, allowed_blocks, default_factory):
        super(MacroBlock, self).__init__()
        self.allowed_blocks = allowed_blocks
        self.default_factory = default_factory

    def add_line(self, line):
        key = None
        dashed = False
        try:
            key, value, dashed = parse(line)
            if dashed and not self.allow_dashes():
                raise MacroParseException()
            factory = self.allowed_blocks[key]
            if not self.repeat_keys():
                self.allowed_blocks.pop(key)
            if value is None:
                child = factory()
            else:
                child = factory(value)
            self.add_child(key, child, dashed)
        except (ValueError, KeyError):
            if self.default_factory is not None:
                child = self.default_factory(line)
                self.add_child(key, child, dashed)
            else:
                raise MacroParseException()

        if child.children is not None:
            return [child] + child.children
        else:
            return [child]

    def get_kwords(self):
        return self.allowed_blocks.keys()

    def repeat_keys(self):
        pass

    def add_child(self, key, value, dashed):
        pass

    def allow_dashes(self):
        return False

    def is_done(self):
        if not self.allowed_blocks and not self.default_factory:
            return True
        else:
            return False


class ListBlock(MacroBlock):
    def __init__(self, allowed_blocks, default_factory):
        self.lines = []
        super(ListBlock, self).__init__(allowed_blocks, default_factory)

    def add_child(self, key, value, dashed):
        if key and (isinstance(value, SingleValue) or
                    isinstance(value, OrbObject)):
            value = KeyPair(key, value)
        self.lines.append(value)

    def serialize(self):
        return [line.serialize() for line in self.lines]

    def repeat_keys(self):
        return True

    @property
    def indent(self):
        return 4


class DictBlock(MacroBlock):
    def __init__(self, allowed_blocks, default_factory):
        self.blocks = utils.UnsortableOrderedDict()
        super(DictBlock, self).__init__(allowed_blocks, default_factory)

    def add_child(self, key, child, dashed):
        self.blocks[key] = child

    def serialize(self):
        res = utils.UnsortableOrderedDict()
        for key, value in self.blocks.iteritems():
            res[key] = value.serialize()
        return res

    def repeat_keys(self):
        return False



class OrbObject(MacroBlock):
    def __init__(self):
        super(OrbObject, self).__init__({}, statement)
        self.blocks = None
        self.lines = None

    @property
    def mode(self):
        if not self.initialized:
            return "uninit"
        elif self.lines:
            return "list"
        else:
            return "dict"

    @property
    def indent(self):
        if not self.initialized:
            return 2
        if self.lines is not None:
            return 4
        else:
            return 2

    @property
    def initialized(self):
        return self.blocks is not None or self.lines is not None

    def allow_dashes(self):
        return True

    def _check_init(self, key, dashed):
        if not self.initialized:
            if key is None:
                if dashed:
                    self.lines = []
                else:
                    raise MacroParseException()
            else:
                self.blocks = utils.UnsortableOrderedDict()
        else:
            if self.lines is None:
                if key is None or dashed:
                    raise MacroParseException()

    def add_child(self, key, child, dashed):
        if key is not None and not isinstance(child, KeyPair):
            child = KeyPair(key, child)

        self._check_init(key, dashed)

        if self.lines is not None:
            self.lines.append(child)
        else:
            if isinstance(child, OrbObject):
                self.blocks[key] = child
            else:
                self.blocks[key] = child.value

    def serialize(self):
        if self.blocks is not None:
            res = utils.UnsortableOrderedDict()
            for key, value in self.blocks.iteritems():
                res[key] = value.serialize()
            return res
        elif self.lines is not None:
            return [line.serialize() for line in self.lines]
        else:
            return None




class CodeBlock(ListBlock):
    def __init__(self):
        super(CodeBlock, self).__init__(get_macro_dicts(), statement)


class NamedBlock(DictBlock):
    def __init__(self, key, value, type, allowed_blocks):
        allowed_blocks[key] = type
        super(NamedBlock, self).__init__(allowed_blocks, None)
        if value:
            self.children = self.add_line(key + ': ' + value)
        else:
            self.children = self.add_line(key + ':')


class IfBlock(NamedBlock):
    def __init__(self, condition):
        super(IfBlock, self).__init__('If', condition, SingleValue,
                                      {'Then': CodeBlock,
                                       'Else': CodeBlock})


class WhileBlock(NamedBlock):
    def __init__(self, condition):
        super(WhileBlock, self).__init__('While', condition, SingleValue,
                                         {'Do': CodeBlock})


class ForBlock(NamedBlock):
    def __init__(self, iterator):
        super(ForBlock, self).__init__('For', iterator, SingleValue,
                                       {
                                           'In': SingleValue,
                                           'Do': CodeBlock
                                       })


class WithBlock(NamedBlock):
    def __init__(self, exception):
        super(WithBlock, self).__init__('With', exception, SingleValue,
                                        {
                                            'As': SingleValue,
                                            'Do': CodeBlock
                                        })


class AsBlock(NamedBlock):
    def __init__(self, exception):
        super(AsBlock, self).__init__('As', exception, SingleValue,
                                      {
                                          'Do': CodeBlock
                                      })


class CatchBlock(ListBlock):
    def __init__(self):
        super(CatchBlock, self).__init__({'With': WithBlock,
                                          'As': AsBlock}, None)


class ExceptionBlock(NamedBlock):
    def __init__(self):
        super(ExceptionBlock, self).__init__('Try', None, CodeBlock,
                                             {
                                                 'Catch': CatchBlock,
                                                 'Else': CodeBlock
                                             })

class DoBlock(NamedBlock):
    def __init__(self):
        super(DoBlock, self).__init__('Do', None, CodeBlock, {})




def statement(value):
    key, value, _ = parse(value)
    if key:
        if value:
            return KeyPair(key, value)
        else:
            return OrbObject()
    else:
        return SingleValue(value)

def get_macro_dicts():
    return {
        'If': IfBlock,
        'While': WhileBlock,
        'For': ForBlock,
        'Try': ExceptionBlock,
        'Do': DoBlock
    }
