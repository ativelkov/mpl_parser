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

import readline
import yaml

import macroparser
import utils



readline.parse_and_bind('tab: complete')
yaml.add_representer(utils.UnsortableOrderedDict,
                     yaml.representer.SafeRepresenter.represent_dict)


def completer(expr, index):
    m = macro_stack[-1]
    kwords = m.get_kwords()
    matching_kwords = [k + ": " for k in kwords if k.startswith(expr)]
    if index < len(matching_kwords):
        return matching_kwords[index]

readline.set_completer(completer)

macro_stack = [macroparser.CodeBlock()]
macro = None
while True:
    if not macro_stack:
        break
    macro = macro_stack[-1]
    if macro.is_done():
        macro_stack.pop()
        continue
    prefix = '(murano) ' if len(macro_stack) == 1 else ' ' * len('(murano) ')
    indents = sum(m.indent for m in macro_stack) - 4

    if isinstance(macro, macroparser.ListBlock) or (
            isinstance(macro, macroparser.OrbObject) and
            macro.lines is not None):
        suffix = '- '
    else:
        suffix = '  '

    prompt = prefix + indents * ' ' + suffix
    line = raw_input(prompt)
    if not line:
        macro_stack.pop()
    else:

        new_macroses = macro.add_line(line)
        if new_macroses:
            macro_stack.extend(new_macroses)

if macro is not None:
    print "Yaml out:"
    print(yaml.dump(macro.serialize(), default_flow_style=False))



