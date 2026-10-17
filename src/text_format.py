# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded text styling without web views, plugins or executable content."""
import re
from pathlib import Path
LIMIT = 128 * 1024
MAX_SPANS = 2000
CODE = {'.py','.js','.ts','.tsx','.jsx','.json','.jsonl','.c','.cpp','.h','.hpp','.rs','.go','.java','.sh','.bash','.sql','.css','.xml','.html','.htm','.yaml','.yml','.toml','.ini','.conf'}
TOKEN = re.compile(r'(?P<string>"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')|(?P<comment>\#[^\n]*|//[^\n]*|/\*[\s\S]*?\*/)|(?P<keyword>\b(?:def|class|return|import|from|if|else|elif|for|while|try|except|with|as|in|not|and|or|None|True|False|function|const|let|var|export|async|await|public|private|void|int|new|SELECT|FROM|WHERE|true|false|null)\b)|(?P<number>\b\d+(?:\.\d+)?\b)')
INLINE = re.compile(r'\*\*([^*\n]+)\*\*|`([^`\n]+)`|(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)|(?<!\*)\*([^*\n]+)\*(?!\*)')


def format_text(path, value):
    suffix = Path(path).suffix.lower()
    text = value['text']
    if len(text) > LIMIT:
        return dict(value, spans=[], note=value['note'] + ' · große Datei: schnelle Rohtextansicht')
    spans = []
    if suffix in ('.md', '.markdown'):
        output = []; offset = 0; fenced = False
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith('```') or line.lstrip().startswith('~~~'):
                fenced = not fenced; continue
            style = 'code' if fenced else None
            if not fenced:
                heading = re.match(r'^ {0,3}(#{1,6})\s+', line)
                if heading: style = 'heading'; line = line[heading.end():]
                elif line.startswith('> '): style = 'quote'; line = line[2:]
                line = re.sub(r'^(\s*)[-+*] ', r'\1• ', line)
            if fenced:
                rendered = line
            else:
                parts = []; position = 0; length = 0
                for match in INLINE.finditer(line):
                    prefix = line[position:match.start()]; parts.append(prefix); length += len(prefix)
                    content = next(group for group in (match[1],match[2],match[3],match[5]) if group is not None)
                    tag = 'bold' if match[1] else 'code' if match[2] else 'link' if match[3] else 'italic'
                    if len(spans) < MAX_SPANS: spans.append((tag,offset+length,offset+length+len(content)))
                    parts.append(content); length += len(content); position = match.end()
                parts.append(line[position:]); rendered = ''.join(parts)
            if style and len(spans) < MAX_SPANS: spans.append((style,offset,offset+len(rendered)))
            output.append(rendered); offset += len(rendered)
        return dict(value, text=''.join(output), spans=spans, note=value['note']+' · Markdown-Leseansicht (ohne externe Inhalte)')
    if suffix in CODE:
        for match in TOKEN.finditer(text):
            spans.append((match.lastgroup,match.start(),match.end()))
            if len(spans) >= MAX_SPANS: break
        return dict(value, spans=spans, note=value['note']+' · Syntaxfarben')
    return dict(value, spans=[])
