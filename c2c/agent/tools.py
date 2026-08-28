"""Tools the caseworker can call.

Design constraint that shapes everything here: **no tool returns a verdict.**

The tempting design is a `check_eligibility(case)` tool backed by a rules
engine. That would make the benchmark a test of whether the agent can call one
function, and would tell us nothing about grounded reasoning. So the tools
retrieve and compute, and the model decides:

  list_documents   what is on file, and by implication what is not
  read_document    one document at a time, in full
  policy_lookup    the exact text of clauses, by id or by keyword
  calculate        exact arithmetic, because the reductions compose

`list_documents` earns its place on absence detection: several cases turn on a
document that should be in the record and is not, and a model reading a long
dossier tends to answer from what is present.
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field
from pathlib import Path

from c2c.models import Case

POLICY_PATH = Path(__file__).resolve().parent.parent.parent / "benchmark" / "POLICY.md"

_CLAUSE_RE = re.compile(r"\*\*(S\d+\.\d+(?:\([a-z]\))?)\*\*")


def _index_policy(text: str) -> dict[str, str]:
    """Split the policy into addressable clauses, keyed by id."""
    hits = list(_CLAUSE_RE.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        out[m.group(1)] = text[m.start() : end].strip()
    return out


_SAFE_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.UAdd: operator.pos, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
}


def safe_eval(expr: str) -> float:
    """Arithmetic only. No names, no calls, no attribute access."""

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return node.value
            raise ValueError("only numbers are allowed")
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](ev(node.operand))
        raise ValueError(f"{type(node).__name__} is not allowed in an expression")

    return ev(ast.parse(expr, mode="eval"))


TOOL_SPEC = """
list_documents()
    Every document on file: id, type, and its first line. Use it to see what is
    in the record, and to notice what is missing from it.

read_document(doc_id)
    The full text of one document.

policy_lookup(query)
    Policy text. Give a clause id such as "S5.4", several separated by commas,
    or a keyword such as "taper" or "duty of care".

calculate(expression)
    Exact arithmetic, e.g. "420 * 0.5" or "210 + 31 + 58 + 21". Numbers and
    operators only.
""".strip()


@dataclass
class ToolBox:
    case: Case
    calls: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._policy_text = POLICY_PATH.read_text()
        self._clauses = _index_policy(self._policy_text)

    def call(self, name: str, args: dict) -> str:
        try:
            fn = getattr(self, f"_t_{name}", None)
            if fn is None:
                out = f"ERROR: no tool named {name!r}. Available: list_documents, read_document, policy_lookup, calculate."
            else:
                out = fn(**args)
        except TypeError as exc:
            out = f"ERROR: bad arguments for {name}: {exc}"
        except Exception as exc:  # noqa: BLE001
            out = f"ERROR: {name} failed: {exc}"
        self.calls.append({"tool": name, "args": args, "result": out})
        return out

    def _t_list_documents(self) -> str:
        lines = [f"{len(self.case.documents)} documents on file for {self.case.case_id}:"]
        for d in self.case.documents:
            first = d.content.splitlines()[0][:90] if d.content else ""
            lines.append(f"  {d.doc_id}  [{d.type}]  {first}")
        if self.case.carrier_response:
            lines.append(f"  (carrier response on file: {self.case.carrier_response.type})")
        else:
            lines.append("  (no carrier response on file)")
        return "\n".join(lines)

    def _t_read_document(self, doc_id: str) -> str:
        for d in self.case.documents:
            if d.doc_id.lower() == str(doc_id).lower():
                return f"--- {d.doc_id} [{d.type}] ---\n{d.content}"
        have = ", ".join(d.doc_id for d in self.case.documents)
        return f"ERROR: no document {doc_id!r} on file. On file: {have}."

    def _t_policy_lookup(self, query: str) -> str:
        wanted = [q.strip() for q in str(query).split(",") if q.strip()]
        found, missing = [], []
        for q in wanted:
            key = q.upper().replace(" ", "")
            if key in self._clauses:
                found.append(self._clauses[key])
            else:
                missing.append(q)
        if missing:
            terms = [m.lower() for m in missing]
            for cid, body in self._clauses.items():
                low = body.lower()
                if any(t in low for t in terms) and body not in found:
                    found.append(body)
        if not found:
            return (f"No policy text matched {query!r}. Clause ids look like S5.4 or S3.2(a). "
                    f"Known parts: {', '.join(sorted({c.split('.')[0] for c in self._clauses}))}.")
        return "\n\n".join(found[:12])

    def _t_calculate(self, expression: str) -> str:
        value = safe_eval(str(expression))
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return f"{expression} = {value}"
