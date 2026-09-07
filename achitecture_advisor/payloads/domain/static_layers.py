"""Bounded Python syntax collectors. Every inferred runtime gap stays explicit."""
import ast
import re
from pathlib import Path


def body_nodes(body):
    for item in body:
        yield item
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            for child in ast.iter_child_nodes(item):
                yield from expression_nodes(child)


def expression_nodes(item):
    yield item
    if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
        for child in ast.iter_child_nodes(item):
            yield from expression_nodes(child)


class Project:
    def __init__(self, sources, modules):
        self.sources, self.modules = sources, modules
        self.trees, self.defs, self.aliases, self.errors = {}, {}, {}, []
        for module, info in modules.items():
            if not info["path"].endswith(".py"):
                continue
            try:
                tree = ast.parse(sources[info["path"]]["text"], filename=info["path"])
                self.trees[module] = tree
                if sources[info["path"]]["text"].splitlines():
                    self.defs[(module, "<module>")] = tree
                self._definitions(module, tree.body, "")
            except SyntaxError as exc:
                self.errors.append(f"{info['path']}:{exc.lineno}: unparsed Python")
        for module, tree in self.trees.items():
            package = module if Path(modules[module]["path"]).stem == "__init__" else module.rpartition(".")[0]
            aliases = {}
            for item in body_nodes(tree.body):
                if isinstance(item, ast.Import):
                    for alias in item.names:
                        aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
                elif isinstance(item, ast.ImportFrom):
                    bits = package.split(".") if package else []
                    prefix = bits[:len(bits)-item.level+1] if item.level and item.level <= len(bits) else []
                    base = ".".join(prefix + ([item.module] if item.module else [])) if item.level else item.module or ""
                    for alias in item.names:
                        if alias.name != "*":
                            aliases[alias.asname or alias.name] = (base + "." + alias.name).strip(".")
            self.aliases[module] = aliases

    def _definitions(self, module, body, prefix):
        for item in body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + item.name
                self.defs[(module, name)] = item
                self._definitions(module, item.body, name + ".")
            else:
                for field in ("body", "orelse", "finalbody"):
                    nested = getattr(item, field, [])
                    if isinstance(nested, list):
                        self._definitions(module, nested, prefix)

    def key(self, module, name):
        return f"symbol:{module}:{name}"

    def resolve(self, module, owner, expression):
        value = expression if isinstance(expression, str) else ast.unparse(expression)
        if value.startswith("self.") or value.startswith("cls."):
            candidate = owner.rpartition(".")[0] + value[value.index("."):]
            if (module, candidate) in self.defs:
                return module, candidate
        prefix = owner.rpartition(".")[0]
        while prefix:
            if (module, prefix + "." + value) in self.defs:
                return module, prefix + "." + value
            prefix = prefix.rpartition(".")[0]
        if (module, value) in self.defs:
            return module, value
        head, sep, tail = value.partition(".")
        full = self.aliases.get(module, {}).get(head, head) + (sep + tail if sep else "")
        for candidate in sorted(self.modules, key=len, reverse=True):
            if full.startswith(candidate + ".") and (candidate, full[len(candidate)+1:]) in self.defs:
                return candidate, full[len(candidate)+1:]
        return None

    def scopes(self, module=None):
        for (mod, name), item in self.defs.items():
            if module not in (None, "*", mod) or isinstance(item, ast.ClassDef):
                continue
            yield mod, name, item


def symbols(records, project):
    for (module, name), item in project.defs.items():
        path = project.modules[module]["path"]
        line = getattr(item, "lineno", 1)
        eid = records.cite(path, line, detail=f"declaration {name}")
        key = records.node(project.key(module, name), "Symbol", name=name.split(".")[-1], qualified_name=module + "." + name,
                           module=module, path=path, line=line, end_line=getattr(item, "end_lineno", len(project.sources[path]["text"].splitlines())),
                           category=type(item).__name__, evidence_id=eid)
        records.edge("module:" + module, key, "DECLARES", eid)
        if "." in name and (module, name.rpartition(".")[0]) in project.defs:
            records.edge(project.key(module, name.rpartition(".")[0]), key, "CONTAINS", eid)
    for module, name, item in project.scopes():
        for use in body_nodes(item.body):
            if isinstance(use, ast.Name) and isinstance(use.ctx, ast.Load):
                resolved = project.resolve(module, name, use)
                if resolved:
                    eid = records.cite(project.modules[module]["path"], use.lineno, detail="lexical reference candidate")
                    records.edge(project.key(module, name), project.key(*resolved), "REFERENCES", eid)
    records.details.update(parsed_python_modules=len(project.trees), warnings=project.errors)


def dependencies(records, project):
    unresolved = []
    for module, tree in project.trees.items():
        for item in ast.walk(tree):
            names = []
            if isinstance(item, ast.Import):
                names = [a.name for a in item.names]
            elif isinstance(item, ast.ImportFrom):
                package = module if Path(project.modules[module]["path"]).stem == "__init__" else module.rpartition(".")[0]
                bits = package.split(".") if package else []
                prefix = bits[:len(bits)-item.level+1] if item.level and item.level <= len(bits) else []
                base = ".".join(prefix + ([item.module] if item.module else [])) if item.level else item.module or ""
                names = [(base + "." + a.name).strip(".") if a.name != "*" else base for a in item.names]
            for imported in names:
                target = imported if imported in project.modules else imported.rpartition(".")[0]
                if target in project.modules and target != module:
                    eid = records.cite(project.modules[module]["path"], item.lineno, item.end_lineno, detail=f"static import {imported}")
                    records.edge("module:" + module, "module:" + target, "DEPENDS_ON", eid)
                elif target not in project.modules:
                    unresolved.append({"module": module, "import": imported, "line": item.lineno})
    records.details.update(unresolved_imports=unresolved, warnings=project.errors)


def calls(records, project):
    unresolved = 0
    for module, name, item in project.scopes():
        path = project.modules[module]["path"]
        # A locally assigned/parameter name may shadow an imported/global symbol.
        args = getattr(item, "args", None)
        shadowed = {a.arg for group in ("posonlyargs", "args", "kwonlyargs") for a in getattr(args, group, [])}
        shadowed.update(a.arg for a in (getattr(args, "vararg", None), getattr(args, "kwarg", None)) if a)
        if not isinstance(item, ast.Module):
            shadowed.update(a.asname or a.name.split(".")[0] for n in body_nodes(item.body) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names)
        shadowed.update(n.id for n in body_nodes(item.body) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store))
        for call in body_nodes(item.body):
            if not isinstance(call, ast.Call):
                continue
            value = ast.unparse(call.func)
            head = value.split(".")[0]
            target = project.resolve(module, name, call.func) if head not in shadowed or head in {"self", "cls"} else None
            eid = records.cite(path, call.lineno, call.end_lineno, detail=f"call expression {value}; static candidate")
            if target:
                records.edge(project.key(module, name), project.key(*target), "CALLS", eid, detail="statically resolved candidate, not observed invocation")
            else:
                key = records.node(f"callsite:{module}:{call.lineno}:{call.col_offset}", "CallSite", name=value, module=module, path=path,
                                   line=call.lineno, resolution="unresolved dispatch or external capability")
                records.edge(project.key(module, name), key, "CALLS_UNRESOLVED", eid)
                unresolved += 1
    records.details["unresolved_calls"] = unresolved


def types(records, project):
    for (module, name), item in project.defs.items():
        source = project.key(module, name)
        values = []
        if isinstance(item, ast.ClassDef):
            values += [(base, "EXTENDS") for base in item.bases]
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            values += [(a.annotation, "ACCEPTS_TYPE") for a in [*item.args.posonlyargs, *item.args.args, *item.args.kwonlyargs] if a.annotation]
            if item.returns:
                values.append((item.returns, "RETURNS"))
        for value, relation in values:
            text = value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else ast.unparse(value)
            found = project.resolve(module, name, text)
            target = project.key(*found) if found else records.node("type:" + text, "Type", name=text)
            eid = records.cite(project.modules[module]["path"], getattr(value, "lineno", item.lineno), detail="explicit type expression")
            records.edge(source, target, relation, eid)
        if not isinstance(item, ast.ClassDef):
            for call in body_nodes(item.body):
                if isinstance(call, ast.Call):
                    found = project.resolve(module, name, call.func)
                    if found and isinstance(project.defs[found], ast.ClassDef):
                        eid = records.cite(project.modules[module]["path"], call.lineno, detail="class constructor syntax")
                        records.edge(source, project.key(*found), "INSTANTIATES", eid)


def state(records, project):
    for module, name, item in project.scopes():
        path = project.modules[module]["path"]
        for node in body_nodes(item.body):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"execute", "executemany"} and node.args:
                sql = node.args[0]
                if not isinstance(sql, ast.Constant) or not isinstance(sql.value, str):
                    continue
                for match in re.finditer(r"\b(FROM|JOIN|UPDATE|INTO)\s+[\"`\[]?([\w.]+)", sql.value, re.I):
                    name_token, table = match.group(1).upper(), match.group(2)
                    relation = "WRITES" if name_token in {"UPDATE", "INTO"} else "READS"
                    if name_token == "FROM" and re.match(r"\s*DELETE\b", sql.value, re.I):
                        relation = "DELETES"
                    target = records.node("table:" + table, "Table", name=table, identity_basis="SQL literal name; physical database unresolved")
                    eid = records.cite(path, node.lineno, node.end_lineno, detail=f"SQL literal {relation}: {table}")
                    records.edge(project.key(module, name), target, relation, eid)
                    records.edge("module:" + module, target, relation, eid)
                    records.edge("module:" + module, target, "ACCESSES", eid)
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
                target = records.node(f"state:{module}:{name}:{ast.unparse(node)}", "ObjectState", name=ast.unparse(node), module=module)
                eid = records.cite(path, node.lineno, detail="syntactic attribute mutation; business identity unresolved")
                records.edge(project.key(module, name), target, "MUTATES" if isinstance(node.ctx, ast.Store) else "DELETES", eid)


def control_flow(records, project, scope):
    for module, name, fn in project.scopes(scope):
        if isinstance(fn, ast.Module):
            continue
        path = project.modules[module]["path"]
        def block(item):
            return records.node(f"block:{module}:{name}:{item.lineno}:{item.col_offset}", "Block", name=f"{type(item).__name__}@{item.lineno}",
                                module=module, function=name, path=path, line=item.lineno, text=ast.unparse(item).splitlines()[0][:250])
        def sequence(body, previous):
            for item in body:
                key = block(item)
                eid = records.cite(path, item.lineno, detail="syntactic control-flow transition")
                for prior, relation in previous:
                    records.edge(prior, key, relation, eid)
                if isinstance(item, ast.If):
                    previous = sequence(item.body, [(key, "BRANCH_TRUE")]) + (sequence(item.orelse, [(key, "BRANCH_FALSE")]) if item.orelse else [(key, "BRANCH_FALSE")])
                elif isinstance(item, (ast.For, ast.AsyncFor, ast.While)):
                    tails = sequence(item.body, [(key, "BRANCH_TRUE")])
                    for tail, _ in tails:
                        records.edge(tail, key, "LOOP_BACK", eid)
                    previous = sequence(item.orelse, [(key, "BRANCH_FALSE")]) if item.orelse else [(key, "BRANCH_FALSE")]
                elif isinstance(item, (ast.Return, ast.Raise)):
                    previous = []
                elif isinstance(item, (ast.With, ast.AsyncWith)):
                    previous = sequence(item.body, [(key, "NEXT")])
                    records.details["limitations"].append(f"{path}:{item.lineno}: context-manager exit/exception behavior unresolved")
                elif isinstance(item, (ast.Try, ast.TryStar, ast.Break, ast.Continue, ast.Match)):
                    records.details["limitations"].append(f"{path}:{item.lineno}: {type(item).__name__} treated as opaque; paths incomplete")
                    previous = [(key, "NEXT")]
                else:
                    previous = [(key, "NEXT")]
            return previous
        sequence(fn.body, [(project.key(module, name), "ENTERS")])


def data_flow(records, project, scope):
    for module, name, fn in project.scopes(scope):
        path = project.modules[module]["path"]
        def value(text):
            return records.node(f"value:{module}:{name}:{text}", "Value", name=text, module=module, function=name)
        for node in body_nodes(fn.body):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and node.value:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                inputs = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
                if isinstance(node, ast.AugAssign):
                    inputs.add(ast.unparse(node.target))
                for target in targets:
                    for source in inputs:
                        eid = records.cite(path, node.lineno, node.end_lineno, detail="flow-insensitive local assignment dependency")
                        records.edge(value(source), value(ast.unparse(target)), "FLOWS_TO", eid, detail="candidate def-use; no execution ordering or sanitization proof")
            if isinstance(node, ast.Call):
                destination = value(f"call {ast.unparse(node.func)}@{node.lineno}")
                for arg in [*node.args, *[k.value for k in node.keywords]]:
                    for use in ast.walk(arg):
                        if isinstance(use, ast.Name) and isinstance(use.ctx, ast.Load):
                            eid = records.cite(path, node.lineno, node.end_lineno, detail="argument syntactically supplied to call")
                            records.edge(value(use.id), destination, "FLOWS_TO", eid)


def api_events_security(records, project, layer, scope):
    for module, name, fn in project.scopes(scope if layer == "security" else None):
        path = project.modules[module]["path"]
        if layer == "api":
            for decorator in getattr(fn, "decorator_list", []):
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr.lower() in {"get", "post", "put", "delete", "patch", "route"} and decorator.args and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str):
                    endpoint = records.node(f"endpoint:{module}:{decorator.args[0].value}", "Endpoint", name=decorator.args[0].value, module=module)
                    eid = records.cite(path, decorator.lineno, detail="HTTP decorator candidate; framework binding not verified")
                    records.edge(project.key(module, name), endpoint, "EXPOSES", eid)
        for call in body_nodes(fn.body):
            if not isinstance(call, ast.Call):
                continue
            expression = ast.unparse(call.func)
            method = expression.rsplit(".", 1)[-1].lower()
            literal = call.args[0].value if call.args and isinstance(call.args[0], ast.Constant) else None
            relation, kind = None, None
            if layer == "api" and method in {"get", "post", "put", "delete", "patch", "request"} and isinstance(literal, str) and literal.startswith(("http://", "https://")):
                relation, kind = "CALLS_API", "Endpoint"
            if layer == "events" and isinstance(literal, str) and method in {"publish", "send", "emit", "subscribe", "consume"}:
                relation, kind = ("PUBLISHES" if method in {"publish", "send", "emit"} else "CONSUMES"), "Event"
            if layer == "security" and expression in {"eval", "exec", "os.system", "subprocess.run", "subprocess.Popen", "subprocess.call"}:
                relation, kind, literal = "CANDIDATE_SINK", "Capability", expression
            if relation:
                target = records.node(f"{kind.lower()}:{literal}", kind, name=literal)
                eid = records.cite(path, call.lineno, call.end_lineno, detail="syntax candidate; runtime semantics not verified")
                records.edge(project.key(module, name), target, relation, eid, detail="candidate only; no runtime, delivery or security conclusion")


def tests(records, project, known_edges):
    test_keys = {project.key(m, n) for m, n, fn in project.scopes() if n.split(".")[-1].startswith("test_") and not isinstance(fn, ast.Module)}
    from .ingest import logical_id
    ids = {logical_id(key): key for key in test_keys}
    reverse = {logical_id(project.key(m, n)): project.key(m, n) for m, n in project.defs}
    for edge in known_edges:
        if edge["rel_type"] == "CALLS" and edge["src"] in ids and edge["dst"] in reverse:
            for eid in edge["properties"]["evidence_ids"]:
                records.edge(ids[edge["src"]], reverse[edge["dst"]], "TESTS", eid, detail="static test call, not executed coverage")
    for module, name, fn in project.scopes():
        if project.key(module, name) not in test_keys:
            continue
        for node in body_nodes(fn.body):
            if isinstance(node, ast.Assert):
                target = records.node(f"assert:{module}:{node.lineno}", "Assertion", name=ast.unparse(node.test), module=module)
                eid = records.cite(project.modules[module]["path"], node.lineno, node.end_lineno, detail="static assertion")
                records.edge(project.key(module, name), target, "ASSERTS", eid)
