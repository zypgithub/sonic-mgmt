from build.merge.merge_infra.confict_resolver.handler import handleImportConflict, handleListAppendConflict, \
    handleCommentConflict, handleWhitespaceConflict, handleElseConflict
from build.merge.merge_infra.confict_resolver.recongnizer import isImportConflict, isCommentConflict, \
    isListAppendConflict, isWhitespaceConflict

conflictRanges = set()


def conflict_parser(input):  # Finds conflicts in the merge file
    conflicts = []
    conflictStart = -1
    conflictEnd = -1
    conflictMiddle = -1
    local = []
    remote = []
    isLocal = False
    isRemote = False
    for count, line in enumerate(input):
        if "<<<<<<<" in line:
            conflictStart = count + 1
            isLocal = True
        elif "=======" in line:
            conflictMiddle = count + 1
            isLocal = False
            isRemote = True
        elif ">>>>>>>" in line:
            isRemote = False
            conflictEnd = count + 1
            localDiff = []
            remoteDiff = []
            localRemoteCommon = set()

            for line in local:
                if line in remote:
                    localRemoteCommon.add(line)
                else:
                    localDiff.append(line)

            for line in remote:
                if line in local:
                    localRemoteCommon.add(line)
                else:
                    remoteDiff.append(line)

            conflictRanges.update(list((range(conflictStart, conflictEnd + 1))))
            for count, line in enumerate(input):
                if line == "\n" and count in conflictRanges:
                    conflictRanges.remove(count)
            conflicts.append(
                ({"conflictStart": conflictStart, "conflictMiddle": conflictMiddle, "conflictEnd": conflictEnd,
                  "local": local, "remote": remote, "localDiff": localDiff, "remoteDiff": remoteDiff,
                  "localRemoteCommon": localRemoteCommon}))
            conflictStart = -1
            conflictMiddle = -1
            conflictEnd = -1
            local = []
            remote = []
        elif isLocal:
            local.append(line)
        elif isRemote:
            remote.append(line)
    return conflicts


def conflict_differ(conflicts, input, else_handler="ours"):  # Processes the conflicts
    unresolved = 0
    for conflict in conflicts:
        conflictStart = conflict["conflictStart"]
        conflictMiddle = conflict["conflictMiddle"]
        conflictEnd = conflict["conflictEnd"]
        local = conflict["local"]
        remote = conflict["remote"]
        localDiff = conflict["localDiff"]
        remoteDiff = conflict["remoteDiff"]
        localRemoteCommon = conflict["localRemoteCommon"]

        if isWhitespaceConflict(local, remote):
            input[conflictStart - 1:conflictEnd] = handleWhitespaceConflict(local, remote, input, conflictStart,
                                                                            conflictEnd, localDiff, remoteDiff,
                                                                            localRemoteCommon)
        else:
            unresolved += 1
            if else_handler == "ours":
                input[conflictStart - 1:conflictEnd] = local
            elif else_handler == "theirs":
                input[conflictStart - 1:conflictEnd] = remote

    return input, unresolved


def conflict_merger(input):  # Removes the new new lines
    for count, line in enumerate(input):
        if line == "\n" and count + 1 in conflictRanges:
            input[count] = ""
    return '\n'.join(input)


def unparser(input,
             fmerge):  # Converts the tokenized form of the merged code back into non-tokenized string version and writes it to the merge file
    joined = ''.join(input)
    open(fmerge, 'w').write(joined)
    return joined
