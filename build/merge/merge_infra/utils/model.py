from collections import defaultdict
from enum import Enum
from typing import List


class MergeHintEnum(Enum):
    MERGE_SUCCESSFULLY = "Commit %commit_id% merged successfully."
    KEEP_US = "All conflicts of commit %commit_id% should keep our version."
    PARTLY_KEEP_US = "Some conflicts of commit %commit_id% should keep our version, but other files should be handled."
    TOTAL_CONFLICT = "There are conflicts with commit %commit_id% and can not be solved automatically."
    NO_CHANGE = "Commit %commit_id% is no change. Maybe it has already been merged."
    MERGE_FAILED = "Commit %commit_id% merge failed. Details: %error%."
    RESOLVED = "Commit %commit_id% cause conflicts, but all of them are resolved."
    PARTLY_RESOLVED = "Commit %commit_id% cause conflicts, some of them are resolved, but other files should be handled."

    def content(self, **kwargs):
        base = self.value
        for key, value in kwargs.items():
            base = base.replace(f"%{key}%", str(value))
        return base

    @property
    def status(self):
        if self in [MergeHintEnum.KEEP_US, MergeHintEnum.MERGE_SUCCESSFULLY, MergeHintEnum.NO_CHANGE, MergeHintEnum.RESOLVED]:
            return True
        return False


class MergeHint:
    def __init__(self, hint: MergeHintEnum, **kwargs):
        self.hint = hint
        self.parameters = kwargs

    @property
    def content(self):
        return self.hint.content(**self.parameters)

    def __str__(self):
        return self.content

    @property
    def pr_id(self):
        return self.parameters.get("pr_id", None)

    @property
    def commit_id(self):
        return self.parameters.get("commit_id", None)

    @property
    def conflict_files(self):
        return self.parameters.get("conflict_files", [])

    @property
    def affected_files(self):
        return self.parameters.get("affected_files", [])

    @property
    def status(self):
        return self.hint.status


class MergeHintHandler:
    @staticmethod
    def summary_by_commit(hints: List[MergeHint]):
        return {h.commit_id: (h.status, h) for h in hints}

    @staticmethod
    def summary_by_file(hints: List[MergeHint]):
        res = defaultdict(list)
        for hint in hints:
            for file in hint.affected_files:
                res[file].append((hint.status, hint))
            for file in hint.conflict_files:
                res[file].append((hint.status, hint))
        return res
