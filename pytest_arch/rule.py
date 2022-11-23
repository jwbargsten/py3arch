from __future__ import annotations

import sys
from fnmatch import fnmatch
from functools import partial
from types import ModuleType

from pytest_check import check

from pytest_arch.collect import collect_imports, walk

if sys.version_info < (3, 9):
    from typing import List
else:
    List = list


def archrule(name: str, comment: str | None = None) -> Rule:
    """Define a new architectural rule with a name and an optional comment."""
    return Rule(name, comment=comment)


# https://peps.python.org/pep-0451/
# the path is the package path: where the submodules are in
class Rule:
    def __init__(self, name: str, comment: str | None) -> None:
        """Define a new architectural rule with a name and a comment."""
        self.name = name
        self.comment = comment

    def match(self, pattern: str) -> RuleTargets:
        """A glob pattern for modules this rule should match."""
        return RuleTargets(self).match(pattern)

    def exclude(self, pattern: str) -> RuleTargets:
        """A glob pattern for modules this rule should exclude from matching.

        Exclusion takes precedence of matching.
        """
        return RuleTargets(self).exclude(pattern)


class RuleTargets:
    def __init__(self, rule: Rule) -> None:
        self.rule = rule
        self.match_criteria: list[str] = []
        self.exclude_criteria: list[str] = []

    def match(self, pattern: str) -> RuleTargets:
        """A glob pattern for modules this rule should match."""
        self.match_criteria.append(pattern)
        return self

    def exclude(self, pattern: str) -> RuleTargets:
        """A glob pattern for modules this rule should exclude from matching.

        Exclusion takes precedence of matching.
        """
        self.exclude_criteria.append(pattern)
        return self

    def should_not_import(self, pattern: str) -> RuleConstraints:
        """Define a constraint that the defined modules should
        not import modules that match the given pattern.

        Keep in mind that module dependencies are checked transtively.

        E.g. 'mymodule.submodule', 'mymodule.*'
        """
        return RuleConstraints(self.rule, self).should_not_import(pattern)

    def should_import(self, pattern: str) -> RuleConstraints:
        """Define a constraint that the defined modules should
        import modules that match the given pattern.

        Keep in mind that module dependencies are checked transtively.

        E.g. 'mymodule.submodule', 'mymodule.*'
        """
        return RuleConstraints(self.rule, self).should_import(pattern)

    def may_import(self, pattern: str) -> RuleConstraints:
        """Loosen the constraints from should_import and
        should_not_import: modules matching may_import are
        excluded/ignored from the constraint check.
        """
        return RuleConstraints(self.rule, self).may_import(pattern)


class RuleConstraints:
    def __init__(self, rule: Rule, targets: RuleTargets) -> None:
        self.rule = rule
        self.targets = targets
        self.forbidden: list[str] = []
        self.required: list[str] = []
        self.ignored: list[str] = []

    def should_not_import(self, pattern: str) -> RuleConstraints:
        """Define a constraint that the defined modules should
        not import modules that match the given pattern.

        Keep in mind that module dependencies are checked transtively.

        E.g. 'mymodule.submodule', 'mymodule.*'
        """
        self.forbidden.append(pattern)
        return self

    def should_import(self, pattern: str) -> RuleConstraints:
        """Define a constraint that the defined modules should
        import modules that match the given pattern.

        Keep in mind that module dependencies are checked transtively.

        E.g. 'mymodule.submodule', 'mymodule.*'
        """
        self.required.append(pattern)
        return self

    def may_import(self, pattern: str) -> RuleConstraints:
        """Loosen the constraints from should_import and
        should_not_import: modules matching may_import are
        excluded/ignored from the constraint check.
        """
        self.ignored.append(pattern)
        return self

    # def check(self, package: str | ModuleType, *, lazy_imports=True):
    def check(self, package: str | ModuleType, *, type_checking=True) -> None:
        """Check the rule against a package or module."""
        rule_name = self.rule.name
        all_imports = collect_imports(package, partial(walk, type_checking=type_checking))
        match_criteria = self.targets.match_criteria
        exclude_criteria = self.targets.exclude_criteria

        candidates = []
        for mp in match_criteria:
            candidates.extend([k for k in all_imports.keys() if fnmatch(k, mp)])
        for ep in exclude_criteria:
            candidates = [k for k in candidates if not fnmatch(k, ep)]

        check.is_true(
            candidates,
            f"No candidates matched. match criteria: {match_criteria}, exclude_criteria: {exclude_criteria}",
        )

        candidates = sorted(candidates)

        if len(candidates) > 4:
            candidates_to_show = candidates[:2] + ["..."] + candidates[-1:]
        else:
            candidates_to_show = candidates

        print(f"rule {rule_name}: candidates are {candidates_to_show}")

        for c in candidates:
            imports = all_imports[c].get("direct", set()) | all_imports[c].get("transitive", set())

            for constraint in self.ignored:
                imports = {imp for imp in imports if not fnmatch(imp, constraint)}

            for constraint in self.required:
                matches = {imp for imp in imports if fnmatch(imp, constraint)}
                check.is_true(
                    matches,
                    f"rule {rule_name}: module {c} did not import anything that matches /{constraint}/",
                )
            for constraint in self.forbidden:
                matches = {imp for imp in imports if fnmatch(imp, constraint)}
                check.is_false(
                    matches, f"rule {rule_name}: module {c} has forbidden imports {matches} (/{constraint}/)"
                )
