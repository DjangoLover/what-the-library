from __future__ import unicode_literals

from wtl.wtparser.parsers.base import BaseParser
from wtl.wtparser.parsers.regex import RegexParserMixin


class PodfileParser(BaseParser, RegexParserMixin):
    language = 'Objective-C'
    filename = 'Podfile'

    def detect(self, content):
        res = [
            r'''^\s*platform\s+(:ios|:osx)''',
            r'''^\s*xcodeproj\s+`.+`''',
            r'''^\s*target.+do''',
            r'''^\s*post_install\s+do''',
            r'''^\s*pod\s+["'].*['"]''',
        ]
        return self._detect_by_regex(content, res)

    def get_platform(self, lines):
        return self._get_value(
            lines, 'platform', r'^platform\s+:(?P<x>\w+)(\s|,|#|$)')

    def get_version(self, lines):
        return self._get_value(
            lines, 'platform',
            r'^platform\s+:\w+\s*,\s*(?P<quot>"|\')(?P<x>.+)(?P=quot)')

    def get_packages(self, lines):
        res = [self._pod(p) for p in self._lines_startwith(lines, 'pod ')]
        def is_valid(p):
            return p['name'] and (p['version'] or p['version_special'])
        return list(filter(is_valid, res))

    def _pod(self, line):
        args = line[4:].lstrip()
        if ',' not in args:
            name_arg = args
            version = None
            special = 'stable'
        else:
            name_arg, _, rest = [x.strip() for x in args.partition(',')]
            if rest.startswith(':head'):
                version = None
                special = 'latest'
            else:
                version_string = self._match(rest, 'x', self.quoted_re)
                special, version = self._match_groups(version_string,
                                                      self.version_re)

        name = self._match(name_arg, 'x', self.quoted_re)
        return {'name': name,
                'version': version,
                'version_special': special}
