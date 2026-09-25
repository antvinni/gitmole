#!/usr/bin/env python3
"""Structure from tree-sitter: nesting, bumpy roads, complex conditionals, cognitive complexity,
self-admitted debt, definitions per file and the import graph, for eleven languages.

Runs by default since 0.32.0: py-tree-sitter and one grammar per
language (tree-sitter-python, -javascript, -typescript, -go, -rust, -java, -c, -cpp, -ruby, -c-sharp,
-php), each a compiled grammar inside an MIT wheel, so it installs with no compiler and parses with
no network. A language whose grammar is not installed is skipped and counted.

Runs as a pipeline step, `python -m gitmole.structure OUT_DIR [--procs N]`, from inside the
repository, and writes structure.json. Every metric comes from one tree-cursor pass per file (the
documented fast path; node iteration is the cost, not parsing). Results are cached by blob hash under
the platform cache directory, keyed with the analyser's version and the grammar's, so a file that did
not change is not parsed again and the cache never needs invalidating; GITMOLE_CACHE names another
directory, or `off`.

Nothing here keys on a name: node kinds are each language's own declaration of its structure, and the
debt markers are the four tags every ecosystem uses (TODO, FIXME, XXX, HACK), after Maldonado and
Shihab (MTD 2015). Cognitive complexity follows SonarSource's public specification, simplified:
+1 for each branch or loop and for each run of like boolean operators, plus the nesting depth for the
structures that nest; `else if` stays flat. A "bump" is CodeScene's bumpy road: a separate chunk of
logic nested two levels or more inside one function."""
from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from multiprocessing import Pool

try:
    from . import filetypes
except ImportError:  # run as a script: the package directory is sys.path[0]
    import filetypes

ANALYSER = "4"   # bump whenever what a file yields changes (a metric, an import's shape): the cache key carries it
MAX_BYTES = 1_000_000
FUNCTIONS_KEPT = 3000

# extension -> (language, grammar module, the function that returns the language pointer)
GRAMMARS = {
    ".py": ("python", "tree_sitter_python", "language"), ".pyi": ("python", "tree_sitter_python", "language"),
    ".js": ("javascript", "tree_sitter_javascript", "language"), ".mjs": ("javascript", "tree_sitter_javascript", "language"),
    ".cjs": ("javascript", "tree_sitter_javascript", "language"), ".jsx": ("javascript", "tree_sitter_javascript", "language"),
    ".ts": ("typescript", "tree_sitter_typescript", "language_typescript"), ".mts": ("typescript", "tree_sitter_typescript", "language_typescript"),
    ".cts": ("typescript", "tree_sitter_typescript", "language_typescript"), ".tsx": ("tsx", "tree_sitter_typescript", "language_tsx"),
    ".go": ("go", "tree_sitter_go", "language"), ".rs": ("rust", "tree_sitter_rust", "language"),
    ".java": ("java", "tree_sitter_java", "language"), ".c": ("c", "tree_sitter_c", "language"), ".h": ("c", "tree_sitter_c", "language"),
    ".cc": ("cpp", "tree_sitter_cpp", "language"), ".cpp": ("cpp", "tree_sitter_cpp", "language"), ".cxx": ("cpp", "tree_sitter_cpp", "language"),
    ".hpp": ("cpp", "tree_sitter_cpp", "language"), ".hh": ("cpp", "tree_sitter_cpp", "language"), ".hxx": ("cpp", "tree_sitter_cpp", "language"),
    ".rb": ("ruby", "tree_sitter_ruby", "language"), ".cs": ("csharp", "tree_sitter_c_sharp", "language"),
    ".php": ("php", "tree_sitter_php", "language_php"),
}

FUNCTION = {"function_definition", "function_declaration", "function_expression", "arrow_function", "method_definition",
            "generator_function_declaration", "generator_function", "method_declaration", "constructor_declaration", "func_literal",
            "function_item", "closure_expression", "lambda_expression", "method", "singleton_method", "local_function_statement",
            "anonymous_function", "lambda"}
CLASS = {"class_definition", "class_declaration", "class_specifier", "struct_specifier", "struct_item", "enum_item", "trait_item",
         "impl_item", "interface_declaration", "type_declaration", "class", "module", "record_declaration", "enum_declaration"}
# structures that branch and nest (cognitive: +1 plus the nesting depth)
NESTING = {"if_statement", "if_expression", "if", "unless", "for_statement", "for_in_statement", "for_expression", "foreach_statement",
           "enhanced_for_statement", "while_statement", "while_expression", "while", "until", "do_statement", "loop_expression",
           "switch_statement", "switch_expression", "expression_switch_statement", "type_switch_statement", "select_statement",
           "match_expression", "match_statement", "case", "catch_clause", "except_clause", "rescue", "ternary_expression",
           "conditional_expression", "conditional", "try_statement"}
# counted without nesting: the branch that continues one already counted
FLAT = {"else_clause", "elif_clause", "elsif", "else"}
NO_INCREMENT = {"try_statement"}   # the try nests its body; the catch is what Sonar counts
LOGICAL = {"&&", "||", "and", "or"}
DEBT = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")

# --- shapes: an error swallowed, an address in a literal, code left in a comment -----------------
CATCH = {"catch_clause", "except_clause", "rescue"}
BODY = {"block", "statement_block", "compound_statement", "then"}
EMPTY_STATEMENTS = {"pass_statement", "empty_statement"}
STRING = {"string", "string_literal", "interpreted_string_literal", "raw_string_literal", "template_string", "encapsed_string"}
ATTRIBUTE = {"attribute", "attribute_list", "annotation", "marker_annotation", "decorator", "attribute_item"}
_QUOTED = re.compile(r"""^[A-Za-z@$]*(["'`]+)(.*?)\1$""", re.S)
_IPV4 = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?::\d{1,5})?$")
# a comment line that reads as a statement: an assignment, a call, a keyword that opens one, a brace
_CODE_LINE = re.compile(r"""^(?:(?:return|if|elif|else|for|while|import|from|var|let|const|def|function|class|#include|throw|raise|break|continue|await)\b.*[;:{})\]]|[A-Za-z_$][\w.$\[\]]*\s*(?:=|\+=|-=|\|=|:=)\s*\S.*|[\w.$]+(?:\.[\w$]+)*\(.*\)\s*;?|[{}]\s*[;)]?|.*[;{]|\}\s*else\b.*)$""")
_COMMENT_MARK = re.compile(r"^\s*(?://+|/\*+|\*+/?|#+|--|;+) ?")
CODE_SHARE = 0.8   # of a comment block's lines that read as code, for the block to count as code left in a comment
_DIRECTIVE = re.compile(r"^(?:eslint|prettier|istanbul|noqa|type:|pylint|@ts-|jshint|global |c8 |nolint|NOLINT|clang-format|fmt:|pragma|region|endregion|-\*-|SPDX-|Copyright|http)", re.I)


BROAD_PYTHON = {"Exception", "BaseException"}   # the language's own root classes


def _is_empty_catch(node, src: bytes = b"") -> bool:
    """A catch, except or rescue whose body does nothing and says nothing: no statement but `pass`, and
    no comment, since a comment is the author saying the error is ignored on purpose (Sonar's S108).
    Python's `except SomeError: pass` is the language's idiom for an expected failure (EAFP), so there
    only a bare `except:` or one that catches Exception or BaseException counts."""
    if node.type == "except_clause":
        caught = [c for c in node.named_children if c.type not in BODY and c.type != "comment"]
        if caught and not all(_text(src, c).strip("() ") in BROAD_PYTHON or _text(src, c).split(" as ")[0].strip("() ") in BROAD_PYTHON for c in caught):
            return False
    body = None
    for c in node.named_children:
        if c.type == "comment":
            return False
        if c.type in BODY:
            body = c
    if body is None:
        return node.type == "rescue"   # Ruby: an empty rescue has no `then` at all
    for c in body.named_children:
        if c.type == "comment" or c.type not in EMPTY_STATEMENTS:
            return False
    return True


def _address(text: str):
    """The IPv4 address a string literal is, with its port, or None: loopback, the unspecified and
    broadcast addresses, netmasks, the documentation ranges (RFC 5737), a trailing .0 (a network, or a
    four-part version like 1.0.0.0), and a first octet of 0, 1 or 2, which is how an ASN.1 object
    identifier (2.5.4.3) starts, are left out."""
    m = _QUOTED.match(text.strip())
    value = (m.group(2) if m else text).strip()
    ip = _IPV4.match(value)
    if not ip:
        return None
    octets = [int(x) for x in ip.groups()]
    if any(o > 255 for o in octets) or octets[0] <= 2 or octets[0] in (127, 255) or octets[3] in (0, 255):   # 0-2: an object identifier's first arc
        return None
    if octets[:3] in ([192, 0, 2], [198, 51, 100], [203, 0, 113]):
        return None
    return value


def _code_like(line: str) -> bool:
    s = line.strip()
    return bool(s) and not _DIRECTIVE.match(s) and not s.endswith(".") and bool(_CODE_LINE.match(s)) and not re.match(r"^[A-Za-z]+(?: [a-z]+){3,}", s)


def commented_code_lines(text: str) -> int:
    """How many lines of one comment block (a block comment, or a run of line comments on consecutive
    lines) read as code; 0 unless four in five of its lines do and one of them starts right after the
    comment marker, as an editor's comment-out leaves it. Prose with a worked example under it (indented,
    or introduced by a line ending in a colon), and documentation comments, whose examples are meant to
    be there, are not code left behind."""
    if text.lstrip().startswith(("/**", "///", "//!", "#!", "/*!")):
        return 0
    lines = [re.sub(r"\s*\*/\s*$", "", _COMMENT_MARK.sub("", l)) for l in text.split("\n")]
    lines = [l.rstrip() for l in lines if l.strip() and l.strip() not in ("*/", "*")]
    if not lines:
        return 0
    code = [l for l in lines if _code_like(l)]
    if len(code) < CODE_SHARE * len(lines) or not any(not l[:1].isspace() for l in code):
        return 0
    if any(l.strip().endswith(":") and not _code_like(l) for l in lines):
        return 0   # "Build the dispatcher function:" introduces an example
    return len(code)


def cache_root() -> str | None:
    explicit = os.environ.get("GITMOLE_CACHE")
    if explicit == "off":
        return None
    if explicit:
        return explicit
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "gitmole", "structure")


_LANGS = {}


def grammar(ext: str):
    """(language name, tree_sitter.Language, grammar version) for an extension, or None when the
    grammar is not installed."""
    if ext not in GRAMMARS:
        return None
    name, module, fn = GRAMMARS[ext]
    if (module, fn) not in _LANGS:
        try:
            import tree_sitter
            from importlib.metadata import version
            mod = importlib.import_module(module)
            _LANGS[(module, fn)] = (name, tree_sitter.Language(getattr(mod, fn)()), version(module.replace("_", "-")))
        except (ImportError, AttributeError, ValueError, OSError, TypeError):
            _LANGS[(module, fn)] = None
    return _LANGS[(module, fn)]


def available() -> bool:
    try:
        import tree_sitter  # noqa: F401
    except ImportError:
        return False
    return any(grammar(ext) for ext in (".py", ".js", ".go", ".c"))


def _text(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


_NAMES = ("identifier", "field_identifier", "property_identifier", "private_property_identifier", "type_identifier", "constant",
          "name", "qualified_identifier", "destructor_name", "operator_name", "shorthand_property_identifier")


def _named(node, src: bytes):
    for field in ("name", "declarator", "key", "property", "left", "pattern"):
        child = node.child_by_field_name(field)
        while child is not None and child.type in ("function_declarator", "pointer_declarator", "reference_declarator"):
            child = child.child_by_field_name("declarator")
        if child is not None and child.type in _NAMES:
            return _text(src, child)[:120]
    return ""


def _name(node, src: bytes, parent_types: list) -> str:
    """The function's own name, else the name it is bound to: a variable, a class field, an object key,
    an assignment (`const f = () => {}`, `handle = async () => {}`, `{ render() {} }`)."""
    own = _named(node, src)
    if own:
        return own
    parent = node.parent
    if parent is not None and parent.type in ("variable_declarator", "field_definition", "public_field_definition", "pair",
                                              "assignment_expression", "assignment", "property_declaration", "let_declaration"):
        return _named(parent, src)
    return ""


def _logical(node) -> bool:
    if node.type == "boolean_operator":
        return True
    if node.type in ("binary_expression", "binary"):
        op = node.child_by_field_name("operator")
        return op is not None and op.type in LOGICAL
    return False


_TYPE_CHECKING = {"TYPE_CHECKING", "typing.TYPE_CHECKING"}   # PEP 484's constant, False at run time


def _deferred(node, src: bytes, lang: str, in_function: bool) -> bool:
    """Whether an import waits past the moment its file loads: inside a function body, a dynamic import(),
    TypeScript's and Flow's `import type` and `export type` (erased when compiled), a Python import under
    `if TYPE_CHECKING:`. These are how a cycle is broken on purpose, so the cycle rule leaves them out."""
    if in_function:
        return True
    if lang in ("javascript", "typescript", "tsx"):
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            return fn is not None and fn.type == "import"
        # TypeScript's grammar has a `type` keyword; Flow's `import type` and `import typeof`, which erase the same
        # way, reach the JavaScript grammar as an error node holding the one word
        return any((c.type == "type" and not c.is_named) or (c.type == "ERROR" and _text(src, c) in ("type", "typeof"))
                   for c in node.children)
    if lang == "python":
        p = node.parent
        while p is not None:
            if p.type == "if_statement":
                cond = p.child_by_field_name("condition")
                if cond is not None and _text(src, cond) in _TYPE_CHECKING:
                    return True
            p = p.parent
    return False


def _import(node, src: bytes, lang: str):
    """The raw module a node imports, or None: Python's import and from-import, ES imports and
    require(), C and C++ quoted includes, Ruby require and require_relative, and the declarations the
    other languages use, kept raw."""
    t = node.type
    if lang == "python":
        if t == "import_statement":
            return [("abs", _text(src, c)) for c in node.children if c.type in ("dotted_name", "aliased_import")
                    for c in ([c.child_by_field_name("name")] if c.type == "aliased_import" else [c]) if c is not None]
        if t == "import_from_statement":
            mod = node.child_by_field_name("module_name")
            base = _text(src, mod) if mod is not None else ""
            names = [_text(src, c.child_by_field_name("name") if c.type == "aliased_import" else c) for c in node.children_by_field_name("name")]
            return [("from", base, names)]
        return None
    if lang in ("javascript", "typescript", "tsx"):
        if t in ("import_statement", "export_statement"):
            source = node.child_by_field_name("source")
            return [("path", _text(src, source).strip("'\"`"))] if source is not None else None
        if t == "call_expression":
            fn = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if fn is not None and _text(src, fn) in ("require", "import") and args is not None and args.named_child_count == 1 \
                    and args.named_children[0].type == "string":
                return [("path", _text(src, args.named_children[0]).strip("'\"`"))]
        return None
    if lang in ("c", "cpp") and t == "preproc_include":
        path = node.child_by_field_name("path")
        if path is not None and path.type == "string_literal":
            return [("include", _text(src, path).strip('"'))]
        return None
    if lang == "ruby" and t == "call":
        method = node.child_by_field_name("method")
        args = node.child_by_field_name("arguments")
        if method is not None and _text(src, method) in ("require", "require_relative") and args is not None and args.named_child_count >= 1:
            first = args.named_children[0]
            if first.type == "string":
                return [("rel" if _text(src, method) == "require_relative" else "req", _text(src, first).strip("'\""))]
        return None
    if t in ("import_spec", "use_declaration", "import_declaration", "using_directive", "namespace_use_declaration",
             "require_once_expression", "require_expression", "include_expression", "include_once_expression"):
        return [("raw", _text(src, node)[:200])]
    return None


class _Func:
    __slots__ = ("name", "start", "end", "nesting", "max_nesting", "cognitive", "complex", "bumps", "chunk")

    def __init__(self, name, start, end):
        self.name, self.start, self.end = name, start, end
        self.nesting = self.max_nesting = self.cognitive = self.complex = self.bumps = 0
        self.chunk = 0


def analyse(src: bytes, lang_name: str, language) -> dict:
    """Every metric for one file, from one cursor walk."""
    import tree_sitter
    tree = tree_sitter.Parser(language).parse(src)
    cursor = tree.walk()
    funcs, stack, done = [], [], []   # stack: one frame per ancestor on the way down
    comments = comment_lines = definitions = 0
    debt, imports, deferred = [], [], []   # deferred: the indices into imports that do not run at load
    shapes = {"empty_catch": [], "bare_except": [], "addresses": [], "commented_code": 0, "commented_sample": []}
    block = []   # the open comment block: [first line, last line, text, made of line comments]

    def flush():
        if block:
            code = commented_code_lines(block[2])
            if code:
                shapes["commented_code"] += code
                if len(shapes["commented_sample"]) < 5:
                    shapes["commented_sample"].append(block[0] + 1)
            block.clear()
    main_guard = False
    chains = []   # open runs of logical operators: [count]
    while True:
        node = cursor.node
        t = node.type if node.is_named else ""   # a keyword token (Ruby's node kinds share the keywords' names) is not a structure
        parent_type = stack[-1][0] if stack else None
        frame = [t, None, False, False, False]   # type, function opened, nested here, chain opened, flat
        current = funcs[-1] if funcs else None
        if t in FUNCTION:
            f = _Func(_name(node, src, [s[0] for s in stack]) or f"(anonymous at line {node.start_point[0] + 1})",
                      node.start_point[0] + 1, node.end_point[0] + 1)
            if current is None:
                definitions += 1
            funcs.append(f)
            frame[1] = f
        elif t in CLASS and stack and all(s[0] in ("program", "module", "source_file", "translation_unit", "compilation_unit", "export_statement",
                                                     "declaration_list", "namespace_declaration") for s in stack):
            definitions += 1   # a class at the top of the file; the root itself (Python's is called module) is not one
        if current is not None and t not in FUNCTION:
            flat_if = t in ("if_statement", "if_expression") and parent_type in FLAT
            if t in FLAT or flat_if:
                current.cognitive += 1
                frame[4] = True
            elif t in NESTING:
                if t not in NO_INCREMENT:
                    current.cognitive += 1 + current.nesting
                if current.nesting == 0:
                    current.chunk = 0
                current.nesting += 1
                current.max_nesting = max(current.max_nesting, current.nesting)
                current.chunk = max(current.chunk, current.nesting)
                frame[2] = True
            if _logical(node):
                if not _in_chain(node):   # the top of a run of boolean operators: Sonar's +1 per sequence
                    chains.append([0])
                    frame[3] = True
                    current.cognitive += 1
                if chains:
                    chains[-1][0] += 1
        if "comment" in t:
            comments += 1
            comment_lines += node.end_point[0] - node.start_point[0] + 1
            text = _text(src, node)
            m = DEBT.search(text)
            if m:
                debt.append({"line": node.start_point[0] + 1, "tag": m.group(1), "text": " ".join(text.split())[:100]})
            own_line = not src[src.rfind(b"\n", 0, node.start_byte) + 1:node.start_byte].strip()   # not trailing code
            line_comment = text.startswith(("//", "#", "--")) and "\n" not in text.rstrip()
            if block and line_comment and block[3] and own_line and node.start_point[0] == block[1] + 1:
                block[1], block[2] = node.end_point[0], block[2] + "\n" + text
            else:
                flush()
                if own_line:
                    block.extend([node.start_point[0], node.end_point[0], text, line_comment])
        elif t in CATCH and _is_empty_catch(node, src):
            shapes["empty_catch"].append(node.start_point[0] + 1)
            if t == "except_clause" and not any(c.type not in BODY and c.type != "comment" for c in node.named_children):
                shapes["bare_except"].append(node.start_point[0] + 1)
        elif t in STRING and node.end_byte - node.start_byte <= 30 and not any(s[0] in ATTRIBUTE for s in stack):
            value = _address(_text(src, node))
            if value:
                shapes["addresses"].append({"line": node.start_point[0] + 1, "value": value})
        found = _import(node, src, lang_name)
        if found:
            if _deferred(node, src, lang_name, current is not None):
                deferred.extend(range(len(imports), len(imports) + len(found)))
            imports.extend(found)
        if lang_name == "python" and t == "if_statement" and not funcs:
            cond = node.child_by_field_name("condition")
            if cond is not None and "__name__" in _text(src, cond) and "__main__" in _text(src, cond):
                main_guard = True
        stack.append(frame)
        if cursor.goto_first_child():
            continue
        while True:
            _leave(stack.pop(), funcs, done, chains)
            if cursor.goto_next_sibling():
                break
            if not cursor.goto_parent():
                flush()
                return _result(done, comments, comment_lines, definitions, debt, imports, deferred, main_guard, src, tree, shapes)


def _in_chain(node) -> bool:
    """Whether a boolean operator continues its parent's run (a && b && c), past parentheses."""
    p = node.parent
    while p is not None and p.type == "parenthesized_expression":
        p = p.parent
    return p is not None and _logical(p)


def _leave(frame, funcs, done, chains):
    t, opened, nested, chain, _ = frame
    if chain and chains:
        count = chains.pop()[0]
        if count >= 3 and funcs:
            funcs[-1].complex += 1
    if nested and funcs:
        f = funcs[-1]
        f.nesting -= 1
        if f.nesting == 0 and f.chunk >= 2:
            f.bumps += 1
    if opened is not None:
        done.append(funcs.pop())


def _result(done, comments, comment_lines, definitions, debt, imports, deferred, main_guard, src, tree, shapes) -> dict:
    lines = src.count(b"\n") + (1 if src and not src.endswith(b"\n") else 0)
    return {"lines": lines, "comments": comments, "comment_lines": comment_lines, "definitions": definitions,
            "debt": debt, "imports": imports, "deferred": deferred, "main": main_guard or src.startswith(b"#!"), "errors": tree.root_node.has_error, "shapes": shapes,
            "functions": [{"name": f.name, "start": f.start, "end": f.end, "nesting": f.max_nesting, "cognitive": f.cognitive,
                           "complex_conditions": f.complex, "bumps": f.bumps} for f in done]}


def _job(item):
    path, sha, ext, data, cache = item
    g = grammar(ext)
    if g is None:
        return path, None, False
    name, language, gver = g
    key = None
    if cache:
        key = os.path.join(cache, f"{ANALYSER}-{name}-{gver}", sha[:2], f"{sha}.json")
        try:
            with open(key, encoding="utf-8") as fh:
                return path, json.load(fh), True
        except (OSError, ValueError):
            pass
    try:
        result = analyse(data, name, language)
    except (ValueError, RecursionError, UnicodeError) as e:   # a grammar that refuses a file costs that file only
        result = {"failed": str(e)[:200]}
    result["language"] = name
    if key:
        try:
            os.makedirs(os.path.dirname(key), exist_ok=True)
            tmp = f"{key}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(result, fh)
            os.replace(tmp, key)
        except OSError:
            pass
    return path, result, False


# --- the import graph ---------------------------------------------------------------------------

_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")


def _python_candidates(path: str, entry, names_only: bool = False) -> list:
    """Paths a Python import could name: `a.b` as a/b.py or a/b/__init__.py; a from-import's module the
    same way, relative dots climbing from the importing file's package, and with `names_only` the
    imported names taken as modules of that package instead."""
    kind = entry[0]
    if kind == "abs":
        mods = [entry[1].replace(".", "/")]
    else:
        base, names = entry[1], entry[2]
        dots = len(base) - len(base.lstrip("."))
        rest = base[dots:].replace(".", "/")
        if dots:
            root = os.path.dirname(path)
            for _ in range(dots - 1):
                root = os.path.dirname(root)
            rest = os.path.normpath(os.path.join(root, rest)) if rest else root
            rest = "" if rest == "." else rest
        mods = [f"{rest}/{n}" if rest else n for n in names] if names_only else [rest]
    return [c for m in mods if m for c in (f"{m}.py", f"{m}/__init__.py")]


def resolve(files: dict, eager: bool = False) -> tuple:
    """(edges {path: sorted imported paths}, resolved share per language); with `eager`, the edges leave
    out the imports marked deferred (see _deferred), while the share stays over every import. Crude on purpose: a
    relative ES import against the directory with the usual extensions and index files, a Python
    module by its path from a root (the tree's top, or any directory no package sits above, so src/
    layouts and test directories resolve and a module inside a package is reached only through the
    package's name), a quoted include against the directory and then by suffix, Ruby's
    require_relative against the directory. Go, Rust, Java, C# and PHP module systems need the build,
    and their imports stay raw."""
    tracked = set(files)
    by_suffix = {}
    for p in sorted(tracked):   # sorted, not set order: two files can answer one suffix (django has two json.py),
        parts = p.split("/")    # and the first candidate wins, so hash order would make the import graph vary per run
        for i in range(len(parts)):
            by_suffix.setdefault("/".join(parts[i:]), []).append(p)
    # An absolute Python import resolves against a sys.path root: the tree's top, src/, a test directory pytest
    # puts on the path. Which directories can be roots is what a package marker decides: a directory holding
    # __init__.py is a package, everything under it is reached through the package's name, so a file's
    # possible roots are its ancestors down to the directory above the outermost package it sits in — and
    # every ancestor when no package sits above it (a namespace layout). By suffix alone, django's
    # `import django` resolved to django/template/backends/django.py and the standard library's `import
    # warnings` to django/utils/warnings.py; checking only the parent directory left the same edges alive one
    # level down, in a package's namespace subdirectories.
    packages = {os.path.dirname(p) for p in tracked if os.path.basename(p) == "__init__.py"} - {""}
    by_module = {}   # module path from some root -> the files that answer it, sorted so the first wins the same way every run
    for p in sorted(tracked):
        if p.endswith(".py"):
            dirs = p.split("/")[:-1]
            cuts = len(dirs)   # no package above: any ancestor may be the root
            for i in range(1, len(dirs) + 1):
                if "/".join(dirs[:i]) in packages:
                    cuts = i - 1   # the outermost package's parent is the deepest root
                    break
            parts = p.split("/")
            for i in range(cuts + 1):
                by_module.setdefault("/".join(parts[i:]), []).append(p)
    # the top-level names a Python import can reach in this tree, so the standard library and installed
    # packages are not counted as imports that failed to resolve
    local_tops = {m.split("/", 1)[0].split(".", 1)[0] for m in by_module}
    edges, tried, hit = {}, Counter(), Counter()
    for path, info in files.items():
        lang = info.get("language")
        out = set()
        lazy = set(info.get("deferred") or ()) if eager else ()
        for i, entry in enumerate(info.get("imports") or []):
            kind = entry[0]
            if kind == "raw":
                continue
            candidates = []
            if lang == "python":
                top = entry[1].lstrip(".").split(".", 1)[0]
                if not entry[1].startswith(".") and top not in local_tops:
                    continue   # the standard library or an installed package
                relative = entry[1].startswith(".")

                def lookup(candidates):   # a relative import names one tree path exactly; an absolute one a module path under some root
                    if relative:
                        return [c for c in candidates if c in tracked and c != path]
                    return [p for c in candidates for p in by_module.get(c, []) if p != path]
                found = []
                if kind == "from" and entry[2]:   # `from pkg import mod`: the module, when the name is one, not pkg/__init__.py
                    found = lookup(_python_candidates(path, (kind, entry[1], entry[2]), names_only=True))
                if not found:
                    found = lookup(_python_candidates(path, (kind, entry[1], [])))
            elif kind == "path":
                if not entry[1].startswith("."):
                    continue   # a package from node_modules, not this tree
                base = os.path.normpath(os.path.join(os.path.dirname(path), entry[1]))
                stem = base[:-3] if base.endswith((".js", ".jsx")) else base   # TypeScript imports name the .js output
                candidates = [base, *(stem + e for e in _JS_EXTS), *(f"{base}/index{e}" for e in _JS_EXTS)]
                found = [c for c in candidates if c in tracked and c != path]
            elif kind == "include":
                local = os.path.normpath(os.path.join(os.path.dirname(path), entry[1]))
                found = [local] if local in tracked else by_suffix.get(entry[1], [])[:1]
            elif kind == "rel":
                local = os.path.normpath(os.path.join(os.path.dirname(path), entry[1]))
                found = [c for c in (local, local + ".rb") if c in tracked]
            elif kind == "req":
                found = by_suffix.get(entry[1] + ".rb", [])[:1]
                if not found:
                    continue   # a gem
            else:
                continue
            tried[lang] += 1
            if found:
                hit[lang] += 1
                if i not in lazy:
                    out.update(found[:1] if lang == "python" and kind == "abs" else found)
        edges[path] = sorted(out)
    return edges, {lang: round(hit[lang] / tried[lang], 3) for lang in tried}


GRAPH_LANGUAGES = {"python", "javascript", "typescript", "tsx"}   # where an unreferenced file can be named with some confidence
MIN_RESOLVED = 0.6   # a language whose imports resolve less often than this has too blind a graph to say "unreferenced"
MIN_FILES = 10


def trusted(files: dict, resolved: dict) -> set:
    """The languages whose import graph a rule may lean on: one it resolves by path, whose imports resolved
    at least MIN_RESOLVED of the time, over at least MIN_FILES files. One gate for unreferenced files and for
    the dependents count on --risk, so the two cannot drift apart."""
    counts = Counter(v.get("language") for v in files.values())
    return {lang for lang, n in counts.items() if lang in GRAPH_LANGUAGES and (resolved or {}).get(lang, 0) >= MIN_RESOLVED and n >= MIN_FILES}
MAX_SHARE = 0.05
PLUGIN_SHARE = 0.25
# entry points by ecosystem convention: run, served, collected or routed rather than imported
_ENTRY_STEMS = {"__init__", "__main__", "main", "index", "app", "server", "cli", "setup", "conftest", "manage", "wsgi", "asgi", "noxfile"}
_ENTRY_DIRS = re.compile(r"(^|/)(bin|scripts|tools|migrations|pages|app|routes|\.github|\.storybook)/")
_ENTRY_SUFFIX = re.compile(r"\.(config|stories|d)\.[cm]?[jt]sx?$")
_SCRIPT_VALUE = re.compile(r"""["']([A-Za-z_][\w.]*):[A-Za-z_][\w.]*["']""")


def entry_points(repo: str, tracked: set) -> set:
    """Files a manifest declares as entry points: the modules in pyproject.toml's `mod.sub:func` values
    (scripts, gui-scripts, entry-points), and package.json's main, module, types, bin and exports."""
    out = set()
    for path in tracked:
        name = path.rsplit("/", 1)[-1]
        base = os.path.dirname(path)
        try:
            with open(os.path.join(repo, path), encoding="utf-8", errors="replace") as fh:
                text = fh.read(500_000)
        except OSError:
            continue
        if name == "pyproject.toml":
            for mod in _SCRIPT_VALUE.findall(text):
                stem = mod.replace(".", "/")
                out.update({f"{stem}.py", f"{stem}/__init__.py", f"src/{stem}.py", f"src/{stem}/__init__.py"})
        elif name == "package.json" and "node_modules/" not in path:
            out.add(path)
            try:
                data = json.loads(text)
            except ValueError:
                continue
            values = []

            def walk(v):
                if isinstance(v, str):
                    values.append(v)
                elif isinstance(v, dict):
                    for x in v.values():
                        walk(x)
                elif isinstance(v, list):
                    for x in v:
                        walk(x)
            for key in ("main", "module", "types", "typings", "bin", "exports", "browser"):
                walk(data.get(key))
            for v in values:
                out.add(os.path.normpath(os.path.join(base, v)))
    return out


def unreferenced(files: dict, edges: dict, resolved: dict, entries: set) -> list:
    """Files in Python, JavaScript or TypeScript that nothing in the tree imports and that are not an
    entry point by convention or by declaration: `possibly unreferenced`, never `dead`. A dynamic
    import, a plugin loaded by name or a framework's file routing does not show in an import graph, so
    only languages whose imports mostly resolve are judged."""
    imported = {t for targets in edges.values() for t in targets}
    judged = trusted(files, resolved)
    names = Counter(p.rsplit("/", 1)[-1] for p in files)
    package_dirs = {os.path.dirname(p) for p in entries_dirs(entries)}
    by_dir = {}
    for p in files:
        by_dir.setdefault(os.path.dirname(p), []).append(p)
    # a directory of three or more files of which the code itself (tests aside) imports under a quarter is
    # loaded by name: plugins, management commands, template loaders
    from_source = {t for src_path, targets in edges.items() if not filetypes.is_test_path(src_path) for t in targets}
    plugin_dirs = {d for d, ps in by_dir.items() if len(ps) >= 3 and sum(p in from_source for p in ps) < PLUGIN_SHARE * len(ps)}
    out, per_language = [], Counter()
    for path, info in sorted(files.items()):
        lang = info["language"]
        if lang not in judged:
            continue
        base = path.rsplit("/", 1)[-1]
        stem = base.split(".", 1)[0]
        if (path in imported or path in entries or info.get("main") or stem in _ENTRY_STEMS or _ENTRY_DIRS.search(path)
                or _ENTRY_SUFFIX.search(path) or base.startswith(".")          # a dotfile is configuration
                or names[base] >= 3                                             # one name in many directories is loaded by convention
                or os.path.dirname(path) in package_dirs                        # a file beside package.json is the package's surface
                or os.path.dirname(path) in plugin_dirs
                or filetypes.is_test_path(path) or filetypes.is_sample_path(path) or filetypes.is_doc_path(path)):
            continue
        out.append(path)
        per_language[lang] += 1
    # a language where more than one file in twenty looks unreferenced loads code by name here: no list for it
    loud = {lang for lang, n in per_language.items() if n > MAX_SHARE * counts[lang]}
    return [p for p in out if files[p]["language"] not in loud]


def _slim_shapes(s: dict) -> dict:
    """The shapes one file holds, as structure.json keeps them: counts and the first few lines; empty
    lists and zero counts are left out so a clean file costs nothing."""
    out = {}
    for key in ("empty_catch", "bare_except"):
        if s.get(key):
            out[key] = s[key][:5]
            out[key + "_count"] = len(s[key])
    if s.get("addresses"):
        out["addresses"] = s["addresses"][:5]
        out["addresses_count"] = len(s["addresses"])
    if s.get("commented_code"):
        out["commented_code"] = s["commented_code"]
        out["commented_sample"] = s.get("commented_sample") or []
    return out


def entries_dirs(entries: set) -> set:
    return {e for e in entries if e.endswith("package.json")}


def _blobs(repo: str, paths: list) -> dict:
    """{path: (sha, bytes)} for the tracked files in `paths`, through one cat-file --batch; files over
    MAX_BYTES are left out, since a file that size is data or a bundle. git lists the whole index and the
    paths are matched here: passing them as pathspecs overflows the argument list on a repository whose
    paths are long, which is how Ghidra (12,000 deep Java paths, over the 1 MB macOS limit) lost this step
    entirely with "Argument list too long"."""
    wanted = set(paths)
    out = subprocess.run([*filetypes.GIT, "ls-files", "-s", "-z"], cwd=repo, capture_output=True).stdout
    shas = {}
    for entry in out.split(b"\0"):
        if entry and b"\t" in entry:
            meta, path = entry.split(b"\t", 1)
            name = path.decode("utf-8", "surrogateescape")
            if meta.startswith(b"100") and name in wanted:
                shas[name] = meta.split()[1].decode()
    if not shas:
        return {}
    order = sorted(shas)
    proc = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, capture_output=True, input="\n".join(shas[p] for p in order).encode() + b"\n")
    data, pos, result = proc.stdout, 0, {}
    for p in order:
        end = data.find(b"\n", pos)
        if end < 0:
            break
        header = data[pos:end].split()
        size = int(header[2]) if len(header) == 3 else 0
        if size <= MAX_BYTES:
            result[p] = (shas[p], data[end + 1:end + 1 + size])
        pos = end + 1 + size + 1
    return result


def printable(value):
    """The result with every path in the form the other steps write: a byte that is not UTF-8 becomes U+FFFD.
    git hands paths over as surrogate escapes so they round-trip into argv, but a report holds text, and the
    tables this data joins with (the watch list, the hotspots) already hold the replaced form, so a surrogate
    here would both break the JSON export ("surrogates not allowed") and match nothing."""
    if isinstance(value, str):
        return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    if isinstance(value, dict):
        return {printable(k): printable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [printable(v) for v in value]
    return value


def collect(repo: str, procs: int = None, vendored=()) -> dict:
    paths = [p for p in filetypes.git_paths(repo, "ls-files") if os.path.splitext(p)[1].lower() in GRAMMARS
             and not filetypes.is_vendored(p, vendored) and "node_modules/" not in p]
    blobs = _blobs(repo, paths)
    cache = cache_root()
    items = [(p, sha, os.path.splitext(p)[1].lower(), data, cache) for p, (sha, data) in sorted(blobs.items())]
    files, languages, missing, cached = {}, Counter(), Counter(), 0
    if items:
        with Pool(procs or max(1, (os.cpu_count() or 2) - 2)) as pool:
            for path, result, hit in pool.imap_unordered(_job, items, chunksize=16):
                if result is None:
                    missing[GRAMMARS[os.path.splitext(path)[1].lower()][0]] += 1
                    continue
                files[path] = result
                languages[result["language"]] += 1
                cached += hit
    edges, resolved = resolve(files)
    eager, _ = resolve(files, eager=True)
    orphans = unreferenced(files, edges, resolved, entry_points(repo, set(filetypes.git_paths(repo, "ls-files"))))
    functions = []
    for path in sorted(files):
        for f in files[path].get("functions") or []:
            if f["nesting"] >= 3 or f["cognitive"] >= 15 or f["bumps"] >= 2 or f["complex_conditions"]:
                functions.append({"file": path, **f})
    functions.sort(key=lambda f: (-f["cognitive"], -f["nesting"], f["file"], f["start"]))
    slim = {p: {"language": v["language"], "lines": v.get("lines", 0), "comments": v.get("comments", 0), "comment_lines": v.get("comment_lines", 0),
                "definitions": v.get("definitions", 0), "debt": len(v.get("debt") or []), "debt_sample": (v.get("debt") or [])[:5],
                "main": v.get("main", False), "imports": edges.get(p, []), "errors": v.get("errors", False),
                **({"deferred": lazy} if (lazy := sorted(set(edges.get(p, [])) - set(eager.get(p, [])))) else {}),
                "shapes": _slim_shapes(v.get("shapes") or {}),
                "max_nesting": max((f["nesting"] for f in v.get("functions") or []), default=0),
                "max_cognitive": max((f["cognitive"] for f in v.get("functions") or []), default=0)}
            for p, v in files.items() if "failed" not in v}
    return {"status": "run", "analyser": ANALYSER, "languages": dict(sorted(languages.items())), "missing_grammars": dict(sorted(missing.items())),
            "cached": cached, "resolved": resolved, "files": slim, "functions": functions[:FUNCTIONS_KEPT], "functions_count": len(functions),
            "unreferenced": orphans[:200], "unreferenced_count": len(orphans)}


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    procs = None
    if "--procs" in args:
        i = args.index("--procs")
        procs = int(args[i + 1])
        del args[i:i + 2]
    if len(args) != 1:
        print("usage: structure.py OUT_DIR [--procs N]", file=sys.stderr)
        return 2
    out_dir = args[0]
    if not available():
        result = {"status": "not-installed", "install": "the grammars need Python 3.10 or newer; reinstall gitmole on 3.10+"}
    else:
        meta = {}
        meta_path = os.path.join(out_dir, "meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as fh:
                meta = json.load(fh)
        vendored = filetypes.vendor_dirs({"meta": meta})
        result = collect(os.getcwd(), procs, vendored)
    with open(os.path.join(out_dir, "structure.json"), "w", encoding="utf-8") as fh:
        json.dump(printable(result), fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
