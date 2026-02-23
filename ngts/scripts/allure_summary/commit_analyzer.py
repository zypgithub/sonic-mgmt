"""
Commit Correlation Engine for Test Failure Analysis.

This module correlates test failures with recent git commits to provide
intelligent insights about:
- Which commits might have caused test failures
- Which commits might have fixed previously failing tests
- Potential risk areas based on changed files

Uses NVOS git repository for commit analysis.
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ngts.scripts.allure_summary.logger import get_logger

logger = get_logger()

# Pre-cloned nvos repo (synced by cron) - for product code
NVOS_REPO_PATH = Path("/auto/sw_system_project/NVOS_INFRA/ChipSim/nvos-master/nvos")

# sonic-mgmt repo - for test infrastructure code
SONIC_MGMT_REPO_PATH = Path("/auto/sysgwork/itkoren/sonic-mgmt")


@dataclass
class Commit:
    """Represents a git commit."""
    hash: str
    short_hash: str
    author: str
    date: str
    subject: str
    files_changed: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)  # Derived from files

    def __str__(self):
        return f"{self.short_hash}: {self.subject[:60]}..."


@dataclass
class CommitCorrelation:
    """Correlation between a test and commits."""
    test_name: str
    related_commits: List[Commit] = field(default_factory=list)
    confidence: float = 0.0  # 0-1 confidence score
    reason: str = ""
    is_potential_fix: bool = False
    is_potential_cause: bool = False


def git_cmd(args: List[str], repo_dir: Path = NVOS_REPO_PATH) -> subprocess.CompletedProcess:
    """Run git command with safe.directory config to handle shared repo ownership."""
    if not repo_dir.exists():
        logger.error(f"Git repo not found: {repo_dir}")
        return subprocess.CompletedProcess(args, 1, "", "Repo not found")

    # Create temporary HOME with .gitconfig to bypass ownership check
    tmp_home = Path("/tmp/allure_git_home")
    tmp_home.mkdir(exist_ok=True)
    tmp_gitconfig = tmp_home / ".gitconfig"
    tmp_gitconfig.write_text("[safe]\n\tdirectory = *\n")

    cmd = ["git", "-c", "safe.directory=*"] + args

    # Set environment variables to bypass ownership check
    env = os.environ.copy()
    env['HOME'] = str(tmp_home)
    env['GIT_CONFIG_GLOBAL'] = str(tmp_gitconfig)
    env['GIT_CONFIG_SYSTEM'] = '/dev/null'
    env['GIT_CONFIG_NOSYSTEM'] = '1'

    result = subprocess.run(cmd, cwd=str(repo_dir), capture_output=True, text=True, env=env, timeout=60)
    return result


def extract_version_from_image(image_version: str) -> Optional[str]:
    """Extract version (e.g. '25.03.0104-005') from image version string."""
    if not image_version:
        return None
    # Try different patterns
    patterns = [
        r'(\d+\.\d+\.\d+(?:-\d+)?)',  # Standard: 25.03.0104-005
        r'nvos-amd64-(\d+\.\d+\.\d+(?:-\d+)?)',  # From path
    ]
    for pattern in patterns:
        match = re.search(pattern, image_version)
        if match:
            return match.group(1)
    return image_version  # Return as-is if no pattern matches


def version_to_tag(version: str) -> str:
    """Convert version to git tag format by looking up in repo."""
    # First, try to find the exact tag
    result = git_cmd(['tag', '-l', f'*_{version}', '--sort=-version:refname'])
    if result.returncode == 0 and result.stdout.strip():
        # Return the first matching tag
        return result.stdout.strip().split('\n')[0]

    # Also try with common prefixes for patch versions
    base_version = version.split('-')[0] if '-' in version else version
    result = git_cmd(['tag', '-l', f'*_{base_version}*', '--sort=-version:refname'])
    if result.returncode == 0 and result.stdout.strip():
        tags = result.stdout.strip().split('\n')
        # Find exact or closest match
        for tag in tags:
            if version in tag:
                return tag
        # Return first match as fallback
        return tags[0]

    # Fallback to guessing
    if version.startswith('25.03.'):
        return f"master_{version}"
    elif version.startswith('25.02.6') and int(version.split('.')[2][:4]) >= 6900:
        return f"nvos-25-02-7000_{version}"
    elif version.startswith('25.02.6'):
        return f"nvos-25-02-6100_{version}"
    return f"master_{version}"


def get_commits_between_versions(
    from_version: str,
    to_version: str,
    max_commits: int = 50
) -> List[Commit]:
    """
    Get commits between two versions.

    Args:
        from_version: Previous version (e.g., "25.03.0105")
        to_version: Current version (e.g., "25.03.0106")
        max_commits: Maximum commits to fetch

    Returns:
        List of Commit objects between versions
    """
    from_tag = version_to_tag(from_version)
    to_tag = version_to_tag(to_version)

    logger.info(f"Getting commits between {from_tag}..{to_tag}")

    # Get commit log with format: hash|short|author|date|subject
    result = git_cmd([
        "log", f"{from_tag}..{to_tag}",
        f"--max-count={max_commits}",
        "--pretty=format:%H|%h|%an|%as|%s",
        "--no-merges"
    ])

    if result.returncode != 0:
        logger.warning(f"Git log failed: {result.stderr[:200]}")
        return []

    commits = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('|', 4)
        if len(parts) >= 5:
            commit = Commit(
                hash=parts[0],
                short_hash=parts[1],
                author=parts[2],
                date=parts[3],
                subject=parts[4]
            )
            # Get files changed
            files_result = git_cmd(["show", commit.hash, "--name-only", "--pretty=format:"])
            if files_result.returncode == 0:
                commit.files_changed = [f for f in files_result.stdout.strip().split('\n') if f]
                commit.components = extract_components(commit.files_changed)
            commits.append(commit)

    logger.info(f"Found {len(commits)} commits between versions")
    return commits


def extract_components(files: List[str]) -> List[str]:
    """Extract component names from file paths."""
    components = set()
    for f in files:
        # Common component patterns
        if f.startswith('platform/'):
            components.add('platform')
            if 'firmware' in f.lower() or 'fw.mk' in f:
                components.add('firmware')
        elif f.startswith('src/sonic-'):
            match = re.match(r'src/(sonic-[^/]+)', f)
            if match:
                components.add(match.group(1))
        elif 'issu' in f.lower():
            components.add('issu')
        elif 'interface' in f.lower() or 'port' in f.lower():
            components.add('interface')
        elif 'system' in f.lower():
            components.add('system')
        elif 'test' in f.lower():
            components.add('tests')
    return list(components)


def get_recent_commits(days: int = 7, max_commits: int = 100) -> List[Commit]:
    """Get recent commits from the repository."""
    result = git_cmd([
        "log", f"--since={days} days ago",
        f"--max-count={max_commits}",
        "--pretty=format:%H|%h|%an|%as|%s",
        "--no-merges"
    ])

    if result.returncode != 0:
        logger.warning(f"Git log failed: {result.stderr[:200]}")
        return []

    commits = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('|', 4)
        if len(parts) >= 5:
            commit = Commit(
                hash=parts[0],
                short_hash=parts[1],
                author=parts[2],
                date=parts[3],
                subject=parts[4]
            )
            commits.append(commit)

    return commits


def correlate_test_with_commits(
    test_name: str,
    test_error: str,
    commits: List[Commit]
) -> CommitCorrelation:
    """
    Correlate a test failure with potential commits.

    Uses heuristics to match:
    - Test name components with changed files/components
    - Error keywords with commit messages
    - File paths in test with changed files

    Args:
        test_name: Name of the failing test
        test_error: Error message or traceback
        commits: List of recent commits

    Returns:
        CommitCorrelation with related commits and confidence
    """
    correlation = CommitCorrelation(test_name=test_name)

    # Extract test components from name
    test_parts = set(re.findall(r'[a-z_]+', test_name.lower()))
    keywords = {'interface', 'port', 'issu', 'firmware', 'system', 'platform',
                'transceiver', 'bios', 'cpld', 'sensor', 'health', 'image'}
    test_keywords = test_parts & keywords

    # Score each commit
    scored_commits = []
    for commit in commits:
        score = 0.0
        reasons = []

        # Check if commit subject mentions test-related keywords
        subject_lower = commit.subject.lower()
        for kw in test_keywords:
            if kw in subject_lower:
                score += 0.3
                reasons.append(f"commit mentions '{kw}'")

        # Check if commit changes related components
        for comp in commit.components:
            if comp.lower() in test_parts or any(tp in comp.lower() for tp in test_parts):
                score += 0.2
                reasons.append(f"changes {comp}")

        # Check for fix indicators
        fix_patterns = ['fix', 'resolve', 'patch', 'correct', 'repair', 'solve']
        if any(fp in subject_lower for fp in fix_patterns):
            if any(kw in subject_lower for kw in test_keywords):
                score += 0.3
                correlation.is_potential_fix = True
                reasons.append("appears to be a fix")

        # Check for breaking indicators
        break_patterns = ['refactor', 'change', 'update', 'modify', 'rewrite', 'rework']
        if any(bp in subject_lower for bp in break_patterns):
            score += 0.1
            correlation.is_potential_cause = True
            reasons.append("significant change")

        if score > 0:
            scored_commits.append((commit, score, ', '.join(reasons)))

    # Sort by score and take top matches
    scored_commits.sort(key=lambda x: x[1], reverse=True)
    top_commits = scored_commits[:5]

    if top_commits:
        correlation.related_commits = [c[0] for c in top_commits]
        correlation.confidence = min(top_commits[0][1], 1.0)
        correlation.reason = top_commits[0][2]

    return correlation


def get_sonic_mgmt_commits(days: int = 7, max_commits: int = 30) -> List[Commit]:
    """
    Get recent commits from sonic-mgmt repository (test infrastructure).

    Args:
        days: How many days back to look
        max_commits: Maximum number of commits to return

    Returns:
        List of Commit objects from sonic-mgmt repo
    """
    if not SONIC_MGMT_REPO_PATH.exists():
        logger.warning(f"sonic-mgmt repo not found at {SONIC_MGMT_REPO_PATH}")
        return []

    result = git_cmd([
        "log", f"--since={days} days ago",
        f"--max-count={max_commits}",
        "--pretty=format:%H|%h|%an|%as|%s",
        "--no-merges",
        "--", "ngts/"  # Only look at test code changes
    ], SONIC_MGMT_REPO_PATH)

    if result.returncode != 0:
        logger.warning(f"Failed to get sonic-mgmt commits: {result.stderr[:200]}")
        return []

    commits = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('|', 4)
        if len(parts) >= 5:
            commit = Commit(
                hash=parts[0],
                short_hash=parts[1],
                author=parts[2],
                date=parts[3],
                subject=parts[4]
            )
            # Get files changed
            files_result = git_cmd(
                ["show", commit.hash, "--name-only", "--pretty=format:"],
                SONIC_MGMT_REPO_PATH
            )
            if files_result.returncode == 0:
                commit.files_changed = [f for f in files_result.stdout.strip().split('\n') if f]
                commit.components = extract_components(commit.files_changed)
            commits.append(commit)

    logger.info(f"Found {len(commits)} recent sonic-mgmt commits")
    return commits


@dataclass
class CommitProbability:
    """Probability that a commit caused/fixed a test issue."""
    commit: Commit
    probability: float  # 0.0 to 1.0
    reasons: List[str] = field(default_factory=list)
    is_fix: bool = False  # True if likely a fix, False if likely a cause
    repo: str = "nvos"  # "nvos" or "sonic-mgmt"

    def __str__(self):
        pct = int(self.probability * 100)
        action = "fixed" if self.is_fix else "caused"
        return f"[{pct}%] {self.commit.short_hash} likely {action} - {', '.join(self.reasons)}"


def calculate_commit_probability(
    test_name: str,
    error_message: str,
    commit: Commit,
    is_for_fix: bool = False
) -> CommitProbability:
    """
    Calculate probability that a commit is related to a test result.

    Scoring priority (highest to lowest):
    1. Commit touches the exact test file (90%)
    2. Commit touches files in same test directory (70%)
    3. Commit subject mentions test name keywords (50%)
    4. Changed files contain test keywords (40%)
    5. Component area matching (20%)
    6. Fix/break keywords (10%)

    Args:
        test_name: Name of the test
        error_message: Error message from the test
        commit: Commit to evaluate
        is_for_fix: True if looking for fix, False if looking for cause

    Returns:
        CommitProbability with score and reasons
    """
    score = 0.0
    reasons = []

    test_name_lower = test_name.lower()
    subject_lower = commit.subject.lower()
    error_lower = error_message.lower()
    files_lower = [f.lower() for f in commit.files_changed]
    files_str = ' '.join(files_lower)

    # Extract test name without parameters: test_foo[NVUE] -> test_foo
    base_test_name = re.sub(r'\[.*\]$', '', test_name_lower)

    # Extract meaningful keywords from test name (ignore common words)
    ignore_words = {'test', 'nvue', 'openapi', 'positive', 'negative', 'basic', 'flow', 'config'}
    test_keywords = set(re.findall(r'[a-z]{4,}', base_test_name)) - ignore_words

    # 1. HIGHEST: Commit touches the exact test file (look for test_name in filename)
    for f in files_lower:
        file_basename = f.split('/')[-1].replace('.py', '')

        # Check if file contains the test function name exactly
        if base_test_name in f:
            score = 0.95
            reasons.append(f"modifies file with '{base_test_name}'")
            break

        # Check for test file with shared keywords
        if file_basename.startswith('test_'):
            file_keywords = set(re.findall(r'[a-z]{4,}', file_basename)) - ignore_words
            overlap = test_keywords & file_keywords

            # Count matching keywords - more overlap = higher score
            if len(overlap) >= 2:
                score = max(score, 0.90)
                reasons.append(f"modifies test file: {file_basename} (matches: {', '.join(overlap)})")
            elif len(overlap) >= 1:
                # Single keyword match - still good if it's a significant keyword
                matched_kw = list(overlap)[0]
                if len(matched_kw) >= 4:  # Significant keyword
                    score = max(score, 0.85)
                    reasons.append(f"modifies test file: {file_basename} (matches: {matched_kw})")

    # 2. HIGH: Commit touches files in same test area/directory
    # Map test keywords to likely directories
    dir_map = {
        'mgmt': ['interfaces', 'mgmt', 'eth0'],
        'port': ['interfaces', 'port', 'aggregated'],
        'interface': ['interfaces'],
        'system': ['system'],
        'platform': ['platform'],
        'firmware': ['firmware', 'fw', 'platform'],
        'issu': ['issu', 'upgrade'],
        'gnmi': ['gnmi', 'telemetry'],
        'sensor': ['platform', 'health'],
        'aggregated': ['interfaces', 'aggregated', 'split'],
        'link': ['interfaces'],
        'configure': ['interfaces', 'system'],
        'reboot': ['system', 'reboot'],
        'health': ['health', 'platform'],
    }

    if score < 0.70:
        for f in files_lower:
            if 'tests_nvos/' in f:
                # Extract directory from path
                parts = f.split('/')
                for i, p in enumerate(parts):
                    if p == 'tests_nvos' and i + 1 < len(parts):
                        test_dir = parts[i + 1]
                        # Check if any test keyword maps to this directory
                        for kw in test_keywords:
                            if kw in dir_map:
                                if test_dir in dir_map[kw] or any(d in test_dir for d in dir_map[kw]):
                                    score = max(score, 0.75)
                                    reasons.append(f"changes {test_dir}/ tests (matches '{kw}')")
                                    break
                            elif kw in test_dir or test_dir in kw:
                                score = max(score, 0.70)
                                reasons.append(f"changes {test_dir}/ tests")
                                break

    # 3. MEDIUM-HIGH: Commit subject directly mentions test keywords
    if score < 0.50:
        matched_kw = []
        for kw in test_keywords:
            if len(kw) > 4 and kw in subject_lower:
                matched_kw.append(kw)
        if matched_kw:
            score = max(score, 0.50 + 0.1 * len(matched_kw))
            reasons.append(f"commit mentions: {', '.join(matched_kw)}")

    # 4. MEDIUM: Changed files contain test keywords (non-test files)
    if score < 0.40:
        for kw in test_keywords:
            if len(kw) > 5 and kw in files_str:
                score = max(score, 0.40)
                reasons.append(f"changes files with '{kw}'")
                break

    # 5. Component area matching (small boost)
    component_map = {
        'interface': ['interface', 'port', 'link'],
        'firmware': ['firmware', 'bios', 'cpld', 'asic'],
        'system': ['system', 'reboot', 'health'],
        'platform': ['platform', 'sensor', 'transceiver', 'psu'],
        'gnmi': ['gnmi', 'telemetry', 'grpc'],
        'issu': ['issu', 'upgrade', 'install'],
        'mgmt': ['mgmt', 'management', 'eth0'],
        'aggregated': ['aggregated', 'aport', 'split'],
    }

    for area, keywords in component_map.items():
        if any(kw in test_name_lower for kw in keywords):
            if any(kw in subject_lower or kw in files_str for kw in keywords):
                score = min(score + 0.05, 0.95)  # Cap at 95%
                if f"involves {area}" not in ' '.join(reasons):
                    reasons.append(f"involves {area}")
                break

    # 6. Fix/break keywords (small boost)
    if is_for_fix:
        fix_patterns = ['fix', 'repair', 'resolve', 'correct', 'patch']
        if any(fp in subject_lower for fp in fix_patterns):
            score = min(score + 0.05, 0.95)
            reasons.append("fix commit")
    else:
        break_patterns = ['refactor', 'rewrite', 'remove', 'breaking', 'change behavior']
        if any(bp in subject_lower for bp in break_patterns):
            score = min(score + 0.05, 0.95)
            reasons.append("significant change")

    # Cap final score at 95% (never be 100% certain)
    score = min(score, 0.95)

    return CommitProbability(
        commit=commit,
        probability=score,
        reasons=reasons,
        is_fix=is_for_fix,
        repo="nvos"
    )


def find_likely_cause_commits(
    test_name: str,
    error_message: str,
    commits: List[Commit],
    top_n: int = 1
) -> List[CommitProbability]:
    """
    Find the commit most likely to have caused a test failure.

    Args:
        test_name: Name of the failing test
        error_message: Error message
        commits: List of commits to search (should be from NVOS repo)
        top_n: Number of top matches to return (default 1)

    Returns:
        List with the most likely CommitProbability
    """
    probabilities = []
    for commit in commits:
        prob = calculate_commit_probability(test_name, error_message, commit, is_for_fix=False)
        # De-duplicate reasons
        prob.reasons = list(dict.fromkeys(prob.reasons))
        if prob.probability >= 0.30:  # Only include if reasonably relevant
            probabilities.append(prob)

    # Sort by probability descending
    probabilities.sort(key=lambda x: x.probability, reverse=True)
    return probabilities[:top_n]


def find_likely_fix_commits(
    test_name: str,
    nvos_commits: List[Commit],
    mgmt_commits: List[Commit],
    top_n: int = 1
) -> List[CommitProbability]:
    """
    Find the commit most likely to have fixed a test.

    Searches both NVOS (product fixes) and sonic-mgmt (test fixes).

    Args:
        test_name: Name of the test that started passing
        nvos_commits: Commits from NVOS repo
        mgmt_commits: Commits from sonic-mgmt repo
        top_n: Number of top matches to return (default 1)

    Returns:
        List with the most likely CommitProbability
    """
    probabilities = []

    # Check NVOS commits (product fixes)
    for commit in nvos_commits:
        prob = calculate_commit_probability(test_name, "", commit, is_for_fix=True)
        prob.repo = "nvos"
        prob.reasons = list(dict.fromkeys(prob.reasons))
        if prob.probability >= 0.30:
            probabilities.append(prob)

    # Check sonic-mgmt commits (test fixes) - prioritize these for test fixes
    for commit in mgmt_commits:
        prob = calculate_commit_probability(test_name, "", commit, is_for_fix=True)
        prob.repo = "sonic-mgmt"
        prob.reasons = list(dict.fromkeys(prob.reasons))
        if prob.probability >= 0.30:
            probabilities.append(prob)

    # Sort by probability descending
    probabilities.sort(key=lambda x: x.probability, reverse=True)
    return probabilities[:top_n]


def get_commit_diff(commit_hash: str, repo_path: str, max_lines: int = 100) -> str:
    """Get the diff content of a commit."""
    try:
        result = subprocess.run(
            ['git', 'show', '--stat', '--format=%B', commit_hash],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.split('\n')[:max_lines]
            return '\n'.join(lines)
    except Exception:
        pass
    return ""


def correlate_with_llm(
    test_name: str,
    error_message: str,
    commits: List[Commit],
    repo_path: str,
    llm_client,
    is_fix: bool = True
) -> Optional[CommitProbability]:
    """
    Use LLM to find the most likely commit that caused/fixed a test.

    Args:
        test_name: Name of the test
        error_message: Error message (empty for fixes)
        commits: List of candidate commits
        repo_path: Path to the git repo
        llm_client: LLM client instance
        is_fix: True if looking for fix, False if looking for cause

    Returns:
        The most likely CommitProbability, or None
    """
    if not commits or not llm_client:
        return None

    # Pre-filter to top 5 candidates using heuristic
    candidates = []
    for commit in commits[:20]:  # Check first 20
        prob = calculate_commit_probability(test_name, error_message, commit, is_for_fix=is_fix)
        if prob.probability >= 0.20:
            candidates.append((commit, prob.probability))

    # Sort by probability and take top 5
    candidates.sort(key=lambda x: x[1], reverse=True)
    top_candidates = [c[0] for c in candidates[:5]]

    if not top_candidates:
        return None

    # Get diff content for each candidate
    commit_details = []
    for commit in top_candidates:
        diff = get_commit_diff(commit.hash, repo_path, max_lines=50)
        commit_details.append(f"""
Commit: {commit.short_hash}
Subject: {commit.subject}
Files changed: {', '.join(commit.files_changed[:5])}
Content:
{diff}
---""")

    action = "FIXED" if is_fix else "CAUSED"

    # Try to find which file contains this test
    test_file_hint = ""
    base_test = re.sub(r'\[.*\]$', '', test_name)  # Remove params like [NVUE]
    try:
        result = subprocess.run(
            ['grep', '-rl', f'def {base_test}', 'ngts/'],
            cwd=repo_path, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            test_file = result.stdout.strip().split('\n')[0]
            test_file_hint = f"\nIMPORTANT: The test function '{base_test}' is defined in file: {test_file}"
    except Exception:
        pass

    prompt = f"""You are analyzing git commits to find which one most likely {action} a test.

Test name: {test_name}{test_file_hint}
{f'Error: {error_message[:200]}' if error_message else ''}

Look for commits that:
1. Modify the file containing the test
2. Modify helper functions or imports used by the test
3. Fix issues related to the test's functionality

Candidate commits:
{''.join(commit_details)}

Which commit most likely {action} this test?
Respond with ONLY a JSON object:
{{"commit_hash": "<short_hash>", "probability": <0-100>, "reason": "<one sentence explanation>"}}

If none are likely related, respond: {{"commit_hash": null, "probability": 0, "reason": "No clear match"}}"""

    try:
        messages = [{"role": "user", "content": prompt}]
        response = llm_client.chat_completion(messages, max_tokens=150)
        if response:
            import json
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                data = json.loads(json_match.group())
                commit_hash = data.get('commit_hash')
                probability = data.get('probability', 0) / 100.0
                reason = data.get('reason', '')

                if commit_hash and probability > 0:
                    # Find the matching commit
                    for commit in top_candidates:
                        if commit.short_hash == commit_hash:
                            return CommitProbability(
                                commit=commit,
                                probability=probability,
                                reasons=[reason],
                                is_fix=is_fix,
                                repo="sonic-mgmt" if 'sonic-mgmt' in repo_path else "nvos"
                            )
    except Exception as e:
        logger.debug(f"LLM correlation failed: {e}")

    return None


class CommitAnalyzer:
    """
    Analyzes commits and correlates them with test results.

    Tracks two repositories:
    - nvos: Product code (for failure correlations)
    - sonic-mgmt: Test infrastructure (for fix correlations)

    Usage:
        analyzer = CommitAnalyzer()
        nvos_commits = analyzer.get_commits_for_version("25.03.0106")
        mgmt_commits = analyzer.get_sonic_mgmt_commits()
    """

    def __init__(self, repo_path: Path = NVOS_REPO_PATH):
        self.repo_path = repo_path
        self._commits_cache: Dict[str, List[Commit]] = {}
        self._mgmt_commits_cache: Optional[List[Commit]] = None

    def is_available(self) -> bool:
        """Check if git repo is accessible."""
        return self.repo_path.exists()

    def get_commits_for_version(self, version: str, lookback_days: int = 3) -> List[Commit]:
        """Get commits associated with a version."""
        if version in self._commits_cache:
            return self._commits_cache[version]

        version = extract_version_from_image(version) or version
        tag = version_to_tag(version)

        # Get commits from tag date back N days
        result = git_cmd([
            "log", tag, f"--max-count=50",
            "--pretty=format:%H|%h|%an|%as|%s",
            "--no-merges"
        ], self.repo_path)

        commits = []
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n')[:30]:
                if not line:
                    continue
                parts = line.split('|', 4)
                if len(parts) >= 5:
                    commit = Commit(
                        hash=parts[0],
                        short_hash=parts[1],
                        author=parts[2],
                        date=parts[3],
                        subject=parts[4]
                    )
                    commits.append(commit)

        self._commits_cache[version] = commits
        return commits

    def correlate_failures(
        self,
        failed_tests: List[Tuple[str, str]],  # [(test_name, error_msg), ...]
        commits: List[Commit]
    ) -> List[CommitCorrelation]:
        """
        Correlate multiple test failures with commits.

        Args:
            failed_tests: List of (test_name, error_message) tuples
            commits: List of commits to correlate against

        Returns:
            List of CommitCorrelation objects
        """
        correlations = []
        for test_name, error_msg in failed_tests:
            correlation = correlate_test_with_commits(test_name, error_msg, commits)
            if correlation.related_commits:
                correlations.append(correlation)
        return correlations

    def get_sonic_mgmt_commits(self, days: int = 7) -> List[Commit]:
        """
        Get recent commits from sonic-mgmt repo (test infrastructure).

        Args:
            days: How many days back to look

        Returns:
            List of Commit objects
        """
        if self._mgmt_commits_cache is not None:
            return self._mgmt_commits_cache

        self._mgmt_commits_cache = get_sonic_mgmt_commits(days=days)
        return self._mgmt_commits_cache

    def find_test_fix_commit(self, test_name: str) -> Optional[Commit]:
        """
        Find a sonic-mgmt commit that might have fixed a test.

        Args:
            test_name: Name of the test that started passing

        Returns:
            Most likely fix commit from sonic-mgmt, or None
        """
        mgmt_commits = self.get_sonic_mgmt_commits()
        return correlate_test_fix_with_commits(test_name, mgmt_commits)

    def get_commit_summary_for_llm(self, commits: List[Commit], max_commits: int = 20) -> str:
        """
        Format commits for LLM analysis.

        Returns a concise summary suitable for LLM context.
        """
        if not commits:
            return "No recent commits found."

        lines = [f"Recent {min(len(commits), max_commits)} commits:"]
        for commit in commits[:max_commits]:
            components = ', '.join(commit.components[:3]) if commit.components else 'misc'
            lines.append(f"- [{commit.short_hash}] ({components}) {commit.subject[:80]}")

        return '\n'.join(lines)
