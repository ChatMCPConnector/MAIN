import re
from typing import Dict, List, Set, Tuple, Optional

class ResolutionError(Exception):
    pass

class Version:
    def __init__(self, version_str: str):
        self.original = version_str.strip()
        s = self.original
        
        if s.startswith('v'):
            s = s[1:]
        
        if '+' in s:
            raise ValueError(f"Build metadata not allowed: {self.original}")
        
        self.prerelease = None
        if '-' in s:
            s, prerelease = s.split('-', 1)
            self.prerelease = self._parse_prerelease(prerelease)
        
        parts = s.split('.')
        if len(parts) != 3:
            raise ValueError(f"Invalid version format: {self.original}")
        
        self.major, self.minor, self.patch = self._parse_version_parts(parts)
        self.normalized = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            self.normalized += f"-{'.'.join(self.prerelease)}"
    
    def _parse_version_parts(self, parts: List[str]) -> Tuple[int, int, int]:
        result = []
        for part in parts:
            if not part or not part.isdigit():
                raise ValueError(f"Invalid version part: {part}")
            if len(part) > 1 and part[0] == '0':
                raise ValueError(f"No leading zeros allowed: {part}")
            result.append(int(part))
        return tuple(result)
    
    def _parse_prerelease(self, prerelease: str) -> List[str]:
        if not prerelease:
            raise ValueError("Empty prerelease identifier")
        parts = prerelease.split('.')
        for part in parts:
            if not part:
                raise ValueError("Empty prerelease identifier")
            if not re.match(r'^[0-9A-Za-z-]+$', part):
                raise ValueError(f"Invalid prerelease identifier: {part}")
            if part.isdigit():
                if len(part) > 1 and part[0] == '0':
                    raise ValueError(f"No leading zeros in numeric prerelease: {part}")
        return parts
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Version):
            return False
        return (self.major, self.minor, self.patch, self.prerelease) == \
               (other.major, other.minor, other.patch, other.prerelease)
    
    def __lt__(self, other) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
        
        has_self = self.prerelease is not None
        has_other = other.prerelease is not None
        
        if has_self and not has_other:
            return True
        if not has_self and has_other:
            return False
        
        if has_self and has_other:
            return self._compare_prerelease(self.prerelease, other.prerelease) < 0
        
        return False
    
    def _compare_prerelease(self, pre1: List[str], pre2: List[str]) -> int:
        min_len = min(len(pre1), len(pre2))
        for i in range(min_len):
            p1, p2 = pre1[i], pre2[i]
            is_num1 = p1.isdigit()
            is_num2 = p2.isdigit()
            
            if is_num1 and is_num2:
                n1, n2 = int(p1), int(p2)
                if n1 != n2:
                    return n1 - n2
            elif is_num1:
                return -1
            elif is_num2:
                return 1
            else:
                if p1 != p2:
                    return -1 if p1 < p2 else 1
        
        return len(pre1) - len(pre2)
    
    def __le__(self, other) -> bool:
        return self < other or self == other
    
    def __gt__(self, other) -> bool:
        return not self <= other
    
    def __ge__(self, other) -> bool:
        return not self < other
    
    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, tuple(self.prerelease) if self.prerelease else None))
    
    def __repr__(self) -> str:
        return f"Version({self.original})"

class Constraint:
    def __init__(self, constraint_str: str):
        self.comparators = self._parse(constraint_str.strip())
    
    def _parse(self, s: str) -> List[Dict]:
        if not s:
            raise ValueError("Empty constraint")
        
        parts = [p.strip() for p in re.split(r'\s*,\s*', s)]
        comparators = []
        for part in parts:
            if not part:
                raise ValueError("Empty constraint part")
            comparators.extend(self._parse_comparator(part))
        return comparators
    
    def _parse_comparator(self, part: str) -> List[Dict]:
        part = part.strip()
        
        if part in ('*', 'x', 'X'):
            return [{'op': '>=', 'version': (0, 0, 0), 'exclude_prerelease': True}]
        
        if part.startswith('>='):
            return self._parse_op_version(part[2:], '>=', True)
        elif part.startswith('>'):
            return self._parse_op_version(part[1:], '>', True)
        elif part.startswith('<='):
            return self._parse_op_version(part[2:], '<=', True)
        elif part.startswith('<'):
            return self._parse_op_version(part[1:], '<', True)
        elif part.startswith('='):
            return self._parse_op_version(part[1:], '==', True)
        elif part.startswith('^'):
            return self._parse_caret(part[1:])
        elif part.startswith('~'):
            return self._parse_tilde(part[1:])
        else:
            return self._parse_partial_or_exact(part)
    
    def _parse_op_version(self, s: str, op: str, allow_partial: bool) -> List[Dict]:
        s = s.strip()
        
        if '.' in s:
            parts = s.split('.')
            if len(parts) == 3:
                v = Version(s)
                return [{'op': op, 'version': (v.major, v.minor, v.patch), 
                         'prerelease': v.prerelease}]
            elif len(parts) == 2 and allow_partial:
                return self._parse_partial_comparison(parts, op)
            elif len(parts) == 1 and allow_partial:
                return self._parse_partial_comparison(parts, op)
        
        v = Version(s)
        return [{'op': op, 'version': (v.major, v.minor, v.patch), 
                 'prerelease': v.prerelease}]
    
    def _parse_partial_or_exact(self, s: str) -> List[Dict]:
        s = s.strip()
        
        if '.' in s:
            parts = s.split('.')
            if len(parts) == 3:
                v = Version(s)
                return [{'op': '==', 'version': (v.major, v.minor, v.patch),
                         'prerelease': v.prerelease}]
            elif len(parts) == 2:
                major, minor = parts
                if minor in ('x', 'X'):
                    minor = None
                return self._partial_to_range(major, minor)
            elif len(parts) == 1:
                major = parts[0]
                if major in ('x', 'X'):
                    return [{'op': '>=', 'version': (0, 0, 0), 'exclude_prerelease': True}]
                return self._partial_to_range(major, None)
        
        v = Version(s)
        return [{'op': '==', 'version': (v.major, v.minor, v.patch),
                 'prerelease': v.prerelease}]
    
    def _parse_partial_comparison(self, parts: List[str], op: str) -> List[Dict]:
        if len(parts) == 2:
            major, minor = map(int, parts)
            if op == '>':
                return [{'op': '>=', 'version': (major, minor + 1, 0)}]
            elif op == '>=':
                return [{'op': '>=', 'version': (major, minor, 0)}]
            elif op == '<':
                return [{'op': '<', 'version': (major, minor, 0)}]
            elif op == '<=':
                return [{'op': '<', 'version': (major, minor + 1, 0)}]
        elif len(parts) == 1:
            major = int(parts[0])
            if op == '>':
                return [{'op': '>=', 'version': (major + 1, 0, 0)}]
            elif op == '>=':
                return [{'op': '>=', 'version': (major, 0, 0)}]
            elif op == '<':
                return [{'op': '<', 'version': (major, 0, 0)}]
            elif op == '<=':
                return [{'op': '<', 'version': (major + 1, 0, 0)}]
        raise ValueError(f"Invalid partial comparison: {parts}")
    
    def _partial_to_range(self, major: str, minor: Optional[str]) -> List[Dict]:
        major_int = int(major)
        if minor is not None:
            minor_int = int(minor)
            return [
                {'op': '>=', 'version': (major_int, minor_int, 0)},
                {'op': '<', 'version': (major_int, minor_int + 1, 0)}
            ]
        else:
            return [
                {'op': '>=', 'version': (major_int, 0, 0)},
                {'op': '<', 'version': (major_int + 1, 0, 0)}
            ]
    
    def _parse_caret(self, s: str) -> List[Dict]:
        s = s.strip()
        parts = s.split('.')
        
        if len(parts) == 3:
            major, minor, patch = map(int, parts)
            if major > 0:
                return [
                    {'op': '>=', 'version': (major, minor, patch)},
                    {'op': '<', 'version': (major + 1, 0, 0)}
                ]
            elif minor > 0:
                return [
                    {'op': '>=', 'version': (major, minor, patch)},
                    {'op': '<', 'version': (major, minor + 1, 0)}
                ]
            else:
                return [{'op': '==', 'version': (major, minor, patch)}]
        elif len(parts) == 2:
            major, minor = map(int, parts)
            if major > 0:
                return [
                    {'op': '>=', 'version': (major, minor, 0)},
                    {'op': '<', 'version': (major + 1, 0, 0)}
                ]
            else:
                return [
                    {'op': '>=', 'version': (major, minor, 0)},
                    {'op': '<', 'version': (major, minor + 1, 0)}
                ]
        elif len(parts) == 1:
            major = int(parts[0])
            return [
                {'op': '>=', 'version': (major, 0, 0)},
                {'op': '<', 'version': (major + 1, 0, 0)}
            ]
        raise ValueError(f"Invalid caret constraint: ^{s}")
    
    def _parse_tilde(self, s: str) -> List[Dict]:
        s = s.strip()
        parts = s.split('.')
        
        if len(parts) == 3:
            major, minor, patch = map(int, parts)
            return [
                {'op': '>=', 'version': (major, minor, patch)},
                {'op': '<', 'version': (major, minor + 1, 0)}
            ]
        elif len(parts) == 2:
            major, minor = map(int, parts)
            return [
                {'op': '>=', 'version': (major, minor, 0)},
                {'op': '<', 'version': (major, minor + 1, 0)}
            ]
        elif len(parts) == 1:
            major = int(parts[0])
            return [
                {'op': '>=', 'version': (major, 0, 0)},
                {'op': '<', 'version': (major + 1, 0, 0)}
            ]
        raise ValueError(f"Invalid tilde constraint: ~{s}")
    
    def satisfies(self, version: Version) -> bool:
        for comp in self.comparators:
            if not self._satisfies_comparator(version, comp):
                return False
        return True
    
    def _satisfies_comparator(self, version: Version, comp: Dict) -> bool:
        op = comp['op']
        target = comp['version']
        
        if comp.get('exclude_prerelease') and version.prerelease is not None:
            return False
        
        prerelease_gate = comp.get('prerelease')
        if version.prerelease is not None:
            if prerelease_gate is None:
                if op in ('>=', '>', '<', '<='):
                    return False
        else:
            if prerelease_gate is not None:
                return False
        
        version_tuple = (version.major, version.minor, version.patch)
        
        if op == '==':
            return version_tuple == target
        elif op == '>=':
            return version_tuple >= target
        elif op == '>':
            return version_tuple > target
        elif op == '<=':
            return version_tuple <= target
        elif op == '<':
            return version_tuple < target
        return False

class Registry:
    def __init__(self):
        self._packages: Dict[str, Dict[Version, Dict[str, str]]] = {}
    
    def add(self, name: str, version: str, deps: Optional[Dict[str, str]] = None) -> None:
        v = Version(version)
        
        if name not in self._packages:
            self._packages[name] = {}
        
        if v in self._packages[name]:
            raise ValueError(f"Duplicate version {version} for package {name}")
        
        self._packages[name][v] = deps or {}
    
    def resolve(self, requirements: Dict[str, str]) -> Dict[str, str]:
        if not requirements:
            return {}
        
        result = self._resolve_with_backtracking(requirements)
        
        if result is None:
            raise ResolutionError("Could not resolve dependencies")
        
        return {name: v.normalized for name, v in result.items()}
    
    def _resolve_with_backtracking(self, requirements: Dict[str, str]) -> Optional[Dict[str, Version]]:
        packages = sorted(requirements.keys())
        
        def backtrack(idx: int, current: Dict[str, Version]) -> Optional[Dict[str, Version]]:
            if idx == len(packages):
                return self._check_transitive(current)
            
            package = packages[idx]
            constraint_str = requirements[package]
            
            try:
                constraint = Constraint(constraint_str)
            except ValueError as e:
                raise ValueError(f"Invalid constraint: {e}")
            
            if package not in self._packages:
                raise ResolutionError(f"Unknown package: {package}")
            
            candidates = sorted(
                [v for v in self._packages[package] if constraint.satisfies(v)],
                reverse=True
            )
            
            if not candidates:
                return None
            
            for candidate in candidates:
                new_current = current.copy()
                new_current[package] = candidate
                
                result = backtrack(idx + 1, new_current)
                if result is not None:
                    return result
            
            return None
        
        return backtrack(0, {})
    
    def _check_transitive(self, solution: Dict[str, Version]) -> Optional[Dict[str, Version]]:
        added = True
        while added:
            added = False
            new_packages = {}
            
            for package, version in solution.items():
                if package not in self._packages:
                    continue
                
                deps = self._packages[package].get(version, {})
                for dep_name, dep_constraint_str in deps.items():
                    if dep_name in solution:
                        continue
                    
                    try:
                        dep_constraint = Constraint(dep_constraint_str)
                    except ValueError as e:
                        raise ValueError(f"Invalid dependency constraint: {e}")
                    
                    if dep_name not in self._packages:
                        raise ResolutionError(f"Unknown dependency: {dep_name}")
                    
                    candidates = sorted(
                        [v for v in self._packages[dep_name] if dep_constraint.satisfies(v)],
                        reverse=True
                    )
                    
                    if not candidates:
                        return None
                    
                    new_packages[dep_name] = candidates[0]
            
            if new_packages:
                solution = {**solution, **new_packages}
                added = True
        
        return solution