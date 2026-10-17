# SPDX-License-Identifier: GPL-3.0-or-later
"""One registry shared by recognition, converters and format documentation."""
WRITER = {'.doc', '.docx', '.docm', '.dot', '.dotx', '.dotm', '.odt', '.ott', '.fodt', '.rtf'}
CALC = {'.xls', '.xlsx', '.xlsm', '.xlsb', '.xlt', '.xltx', '.xltm', '.ods', '.ots', '.fods'}
IMPRESS = {'.ppt', '.pptx', '.pptm', '.pps', '.ppsx', '.ppsm', '.pot', '.potx', '.potm', '.odp', '.otp', '.fodp'}
DRAW = {'.odg', '.otg', '.fodg', '.vsd', '.vsdx'}
MATH = {'.odf', '.mml'}
OFFICE_SUFFIXES = WRITER | CALC | IMPRESS | DRAW | MATH
ARCHIVES = {'.zip', '.tar', '.tgz', '.tbz', '.tbz2', '.txz', '.7z', '.rar', '.gz', '.bz2', '.xz'}
AUDIO = {'.mp3', '.flac', '.wav', '.ogg', '.oga', '.opus', '.m4a', '.aac', '.wma', '.aiff', '.aif'}
VIDEO = {'.ts', '.mp4', '.mkv', '.webm', '.mov', '.avi', '.m4v', '.mpg', '.mpeg', '.wmv', '.mts', '.m2ts', '.3gp', '.ogv'}
TEXT_KINDS = {'text', 'epub', 'archive', 'audio', 'info'}
